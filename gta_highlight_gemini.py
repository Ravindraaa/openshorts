"""Gemini semantic review for locally detected GTA gameplay moments."""
from __future__ import annotations
import json, os, subprocess, tempfile, time
from typing import List
from pydantic import BaseModel, Field
from google import genai
from google.genai import types as genai_types
import gemini_worker

class GTAReview(BaseModel):
    candidate_index: int = Field(ge=0)
    keep: bool
    score: int = Field(ge=0,le=100)
    event_type: str
    reason: str
    hook: str

class GTAReviewResponse(BaseModel):
    reviews: List[GTAReview]

GTA_REVIEW_PROMPT = """You are a strict senior editor selecting viral GTA gameplay moments.
Review the montage in order. The manifest maps each montage segment to the original source time.
Prioritize clearly visible payoffs: police chase/escape, explosion, spectacular crash, stunt/jump,
robbery, intense gunfight, unexpected NPC reaction, hilarious fail, physics glitch, near miss,
or unusually chaotic moment. Reject ordinary driving/walking, routine shooting without payoff,
menus/loading, static/repetitive scenes, and footage that is merely loud or visually busy.
Do not invent events. Keep only genuinely entertaining moments. Hook max 8 words.
Candidates:
{candidate_manifest}
Return exactly one review per candidate index, score 0-100; use keep=false for weak moments.
"""

def _make_proxy(source,start,end,output):
    duration=max(.1,float(end)-float(start))
    cmd=["ffmpeg","-nostdin","-y","-v","error","-ss",f"{float(start):.3f}","-i",source,
         "-t",f"{duration:.3f}","-vf","scale=-2:360,fps=1","-an","-c:v","libx264",
         "-preset","veryfast","-crf","31","-pix_fmt","yuv420p","-movflags","+faststart",output]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=180)
    if p.returncode or not os.path.isfile(output) or not os.path.getsize(output):
        raise RuntimeError(f"Candidate proxy failed: {(p.stderr or '')[-400:]}")

def _concat(paths,output):
    listfile=output+".txt"
    with open(listfile,"w",encoding="utf-8") as f:
        for path in paths:
            safe=os.path.abspath(path).replace("\\","/")
            f.write("file '"+safe.replace("'","'\\''")+"'\n")
    try:
        p=subprocess.run(["ffmpeg","-nostdin","-y","-v","error","-f","concat","-safe","0","-i",listfile,"-c","copy",output],
                         capture_output=True,text=True,timeout=180)
        if p.returncode or not os.path.isfile(output) or not os.path.getsize(output):
            raise RuntimeError(f"Montage creation failed: {(p.stderr or '')[-400:]}")
    finally:
        try: os.remove(listfile)
        except OSError: pass

def _clean_reviews(parsed,candidates,min_score=72,max_clips=2):
    reviews={}
    for r in parsed.get("reviews") or []:
        try:
            i=int(r.get("candidate_index",-1))
            if 0<=i<len(candidates): reviews[i]=r
        except (TypeError,ValueError): pass
    picks=[]
    for i,c in enumerate(candidates):
        r=reviews.get(i)
        if not r or not r.get("keep"): continue
        try:
            score=max(0,min(100,int(r.get("score",0))))
            start,end=float(c["start"]),float(c["end"])
        except (KeyError,TypeError,ValueError): continue
        if score<min_score or end<=start: continue
        event=str(r.get("event_type") or "GTA gameplay moment").strip()
        reason=str(r.get("reason") or "").strip(); hook=str(r.get("hook") or "GTA chaos").strip()
        picks.append({"start":round(start,3),"end":round(end,3),"predicted_score":score,
            "gta_event_type":event[:80],"gta_review_reason":reason[:240],
            "video_description_for_tiktok":f"{event}: {reason}".strip(": "),
            "video_description_for_instagram":f"{event}: {reason}".strip(": "),
            "video_title_for_youtube_short":hook[:100],"viral_hook_text":hook[:80]})
    picks.sort(key=lambda x:-x["predicted_score"]); selected=[]
    for item in picks:
        duplicate=any(max(0,min(item["end"],x["end"])-max(item["start"],x["start"]))/
            max(1e-6,min(item["end"]-item["start"],x["end"]-x["start"]))>=.35 for x in selected)
        if not duplicate: selected.append(item)
        if len(selected)>=max_clips: break
    return selected

def review_gta_candidates(video_path,candidates,api_key=None,model_name=None,min_score=72,max_clips=2):
    if not candidates: return {"shorts":[]}
    key=api_key or os.getenv("GEMINI_API_KEY")
    if not key: raise RuntimeError("GEMINI_API_KEY is required for GTA visual verification.")
    model_name=model_name or os.getenv("GEMINI_MODEL") or "gemini-3.1-flash-lite"
    manifest=[]; cursor=0.0
    for i,c in enumerate(candidates):
        d=max(.1,float(c["end"])-float(c["start"]))
        manifest.append(f"{i}: montage {cursor:.1f}-{cursor+d:.1f}s; original {float(c['start']):.1f}-{float(c['end']):.1f}s; activity score {float(c.get('score',0)):.3f}")
        cursor+=d
    with tempfile.TemporaryDirectory(prefix="gta-gemini-review-") as tmp:
        proxies=[]
        for i,c in enumerate(candidates):
            path=os.path.join(tmp,f"candidate_{i:02d}.mp4"); _make_proxy(video_path,c["start"],c["end"],path); proxies.append(path)
        montage=os.path.join(tmp,"gta_candidates.mp4"); _concat(proxies,montage)
        client=genai.Client(api_key=key); uploaded=None
        try:
            uploaded=gemini_worker.upload_media(client,montage); deadline=time.time()+180
            while True:
                info=client.files.get(name=uploaded.name)
                state=str(getattr(getattr(info,"state",info),"name","")).upper()
                if state=="ACTIVE": break
                if state=="FAILED": raise RuntimeError("Gemini could not process GTA montage.")
                if time.time()>deadline: raise TimeoutError("Gemini GTA review timed out.")
                time.sleep(2)
            prompt=GTA_REVIEW_PROMPT.format(candidate_manifest="\n".join(manifest))
            config=genai_types.GenerateContentConfig(response_mime_type="application/json",
                response_schema=GTAReviewResponse,temperature=.1)
            response=client.models.generate_content(model=model_name,contents=[uploaded,prompt],config=config)
            gemini_worker.raise_if_blocked(response)
            parsed_obj=getattr(response,"parsed",None)
            if parsed_obj is not None: parsed=parsed_obj.model_dump() if hasattr(parsed_obj,"model_dump") else parsed_obj
            else:
                response_text=getattr(response,"text",None)
                if not response_text: raise RuntimeError("Gemini returned an empty GTA review response.")
                parsed=json.loads(response_text)
            shorts=_clean_reviews(parsed,candidates,min_score,max_clips)
            cost=gemini_worker._calculate_cost_analysis(response,model_name)
            result={"shorts":shorts}
            if cost: result["cost_analysis"]=cost
            result["gta_highlight_review"]={"candidate_count":len(candidates),"approved_count":len(shorts),"minimum_score":min_score}
            return result
        finally:
            if uploaded is not None:
                try: client.files.delete(name=uploaded.name)
                except Exception: pass
