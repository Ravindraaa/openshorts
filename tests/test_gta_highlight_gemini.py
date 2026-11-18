from gta_highlight_gemini import _clean_reviews

def test_rejects_low_score():
    c=[{"start":10,"end":30,"score":.9}]
    r={"reviews":[{"candidate_index":0,"keep":True,"score":60,"event_type":"chase","reason":"clear","hook":"Police chase"}]}
    assert _clean_reviews(r,c)==[]

def test_keeps_high_score_in_openshorts_shape():
    c=[{"start":10,"end":30,"score":.9}]
    r={"reviews":[{"candidate_index":0,"keep":True,"score":91,"event_type":"Police chase","reason":"Player escapes blockade","hook":"Clean getaway!"}]}
    out=_clean_reviews(r,c)
    assert len(out)==1 and out[0]["start"]==10 and out[0]["predicted_score"]==91
    assert out[0]["viral_hook_text"]=="Clean getaway!"

def test_rejects_out_of_range_index():
    c=[{"start":10,"end":30,"score":.9}]
    r={"reviews":[{"candidate_index":3,"keep":True,"score":99,"event_type":"Explosion","reason":"visible","hook":"Boom"}]}
    assert _clean_reviews(r,c)==[]

def test_deduplicates_and_caps_two():
    c=[{"start":0,"end":20},{"start":2,"end":22},{"start":50,"end":70}]
    r={"reviews":[{"candidate_index":i,"keep":True,"score":s,"event_type":"GTA stunt","reason":"payoff","hook":f"Stunt {i}"} for i,s in enumerate([95,90,85])]}
    out=_clean_reviews(r,c,max_clips=2)
    assert len(out)==2 and [x["start"] for x in out]==[0,50]

def test_empty_reviews():
    assert _clean_reviews({"reviews":[]},[{"start":0,"end":20}])==[]
