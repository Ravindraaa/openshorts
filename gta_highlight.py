"""CPU-friendly activity candidate detection for GTA gameplay clips."""
from __future__ import annotations
import math, os, subprocess
from dataclasses import asdict, dataclass
import cv2
import numpy as np

@dataclass
class HighlightCandidate:
    start: float
    end: float
    score: float
    audio_score: float
    motion_score: float
    scene_score: float
    peak_score: float
    evidence: list[str]
    def to_dict(self):
        return asdict(self)

def _robust_normalize(values):
    x=np.asarray(values,dtype=np.float32)
    if not x.size: return x
    lo,hi=np.percentile(x,[10,95])
    if not np.isfinite(lo) or not np.isfinite(hi) or hi-lo<1e-7: return np.zeros_like(x)
    return np.clip((x-lo)/(hi-lo),0.0,1.0)

def _audio_rms(path,duration,sample_rate=8000):
    seconds=max(1,int(math.ceil(duration)))
    cmd=["ffmpeg","-nostdin","-v","error","-i",path,"-vn","-ac","1","-ar",str(sample_rate),"-f","f32le","-"]
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=max(60,seconds*3),check=False)
        if p.returncode or not p.stdout: return np.zeros(seconds,dtype=np.float32)
        audio=np.frombuffer(p.stdout,dtype="<f4"); out=np.zeros(seconds,dtype=np.float32)
        for i in range(seconds):
            chunk=audio[i*sample_rate:(i+1)*sample_rate]
            if chunk.size: out[i]=float(np.sqrt(np.mean(np.square(chunk,dtype=np.float64))))
        return out
    except (OSError,subprocess.SubprocessError,ValueError):
        return np.zeros(seconds,dtype=np.float32)

def _visual_signals(path,duration,sample_fps=2.0,width=320):
    seconds=max(1,int(math.ceil(duration))); motion=np.zeros(seconds,dtype=np.float32); cuts=np.zeros(seconds,dtype=np.float32)
    cap=cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release(); raise RuntimeError(f"Could not open video: {path}")
    fps=cap.get(cv2.CAP_PROP_FPS)
    if not fps or not np.isfinite(fps) or fps<=0: fps=30.0
    step=max(1,int(round(fps/max(.5,sample_fps)))); prev=None; idx=0
    try:
        while True:
            ok,frame=cap.read()
            if not ok: break
            if idx%step==0:
                t=idx/fps
                if t>=duration: break
                h,w=frame.shape[:2]; tw=min(width,w); th=max(1,int(round(h*tw/max(1,w))))
                gray=cv2.cvtColor(cv2.resize(frame,(tw,th),interpolation=cv2.INTER_AREA),cv2.COLOR_BGR2GRAY)
                sec=min(seconds-1,int(t))
                if prev is not None:
                    v=float(np.mean(cv2.absdiff(gray,prev)))/255.0
                    motion[sec]=max(motion[sec],v); cuts[sec]=max(cuts[sec],max(0.0,(v-.22)/.45))
                prev=gray
            idx+=1
    finally: cap.release()
    return motion,np.clip(cuts,0,1)

def _window_candidates(audio,motion,cuts,duration,min_seconds,max_seconds,top_k,threshold):
    if top_k<=0: return []
    n=max(1,min(len(audio),len(motion),len(cuts)))
    a=_robust_normalize(np.asarray(audio[:n],dtype=np.float32))
    m=_robust_normalize(np.asarray(motion[:n],dtype=np.float32))
    c=_robust_normalize(np.asarray(cuts[:n],dtype=np.float32))
    delta=np.maximum(0.0,a-np.r_[a[:1],a[:-1]]); peak=_robust_normalize(delta)
    min_len=max(5,int(round(min_seconds))); max_len=max(min_len,int(round(max_seconds)))
    stride=max(2,min_len//3); candidates=[]
    for length in sorted({min_len,min(max_len,max(min_len,24)),max_len}):
        if length>n: continue
        for start in range(0,max(1,n-length+1),stride):
            end=min(n,start+length)
            if end-start<min_len: continue
            av=float(np.mean(a[start:end])); mv=float(np.mean(m[start:end]))
            cv=float(np.mean(c[start:end])); pv=float(np.percentile(peak[start:end],90))
            score=.34*av+.34*mv+.14*cv+.18*pv; evidence=[]
            if av>=.55: evidence.append("elevated_audio_energy")
            if mv>=.55: evidence.append("high_visual_motion")
            if cv>=.45: evidence.append("scene_change_activity")
            if pv>=.55: evidence.append("sudden_audio_peak")
            candidates.append(HighlightCandidate(float(start),float(min(end,duration)),round(score,4),
                round(av,4),round(mv,4),round(cv,4),round(pv,4),evidence))
    candidates.sort(key=lambda x:x.score,reverse=True); selected=[]
    for item in candidates:
        if item.score<threshold: continue
        duplicate=False
        for chosen in selected:
            overlap=max(0.0,min(item.end,chosen.end)-max(item.start,chosen.start))
            shorter=max(1e-6,min(item.end-item.start,chosen.end-chosen.start))
            if overlap/shorter>=.45: duplicate=True; break
        if not duplicate: selected.append(item)
        if len(selected)>=top_k: break
    return sorted(selected,key=lambda x:x.start)

def detect_candidates(video_path,duration=None,min_seconds=15.0,max_seconds=35.0,top_k=8,threshold=.28,sample_fps=2.0):
    if not os.path.isfile(video_path): raise FileNotFoundError(video_path)
    if min_seconds<=0 or max_seconds<min_seconds: raise ValueError("Require 0 < min_seconds <= max_seconds")
    if top_k<=0: return []
    if duration is None:
        cap=cv2.VideoCapture(video_path); fps=cap.get(cv2.CAP_PROP_FPS) or 30.0
        count=cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0; cap.release()
        duration=float(count/fps) if count>0 else 0.0
    duration=float(duration)
    if not np.isfinite(duration) or duration<=0: raise ValueError("Could not determine a valid video duration")
    audio=_audio_rms(video_path,duration); motion,cuts=_visual_signals(video_path,duration,sample_fps)
    return [x.to_dict() for x in _window_candidates(audio,motion,cuts,duration,min_seconds,max_seconds,top_k,threshold)]

def candidates_json(video_path,**kwargs):
    import json
    return json.dumps(detect_candidates(video_path,**kwargs),indent=2)
