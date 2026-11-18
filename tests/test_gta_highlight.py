import numpy as np
from gta_highlight import _robust_normalize, _window_candidates

def test_constant_signal_normalizes_to_zero():
    assert np.array_equal(_robust_normalize(np.ones(10)),np.zeros(10))

def test_normalized_signal_is_bounded():
    result=_robust_normalize(np.array([0,1,2,3,100],dtype=np.float32))
    assert np.all(result>=0) and np.all(result<=1) and result[-1]==1

def test_quiet_signals_return_no_candidates():
    z=np.zeros(100,dtype=np.float32)
    assert _window_candidates(z,z,z,100,15,30,5,.5)==[]

def test_candidates_are_deduplicated():
    a=np.zeros(100,dtype=np.float32); m=a.copy(); c=a.copy()
    a[30:60]=1; m[30:60]=1; c[30:60]=1
    got=_window_candidates(a,m,c,100,15,30,8,.2)
    for i,x in enumerate(got):
        for y in got[i+1:]:
            overlap=max(0,min(x.end,y.end)-max(x.start,y.start))
            shorter=min(x.end-x.start,y.end-y.start)
            assert overlap/max(shorter,1e-6)<.45

def test_zero_top_k_returns_empty():
    z=np.zeros(60,dtype=np.float32)
    assert _window_candidates(z,z,z,60,15,30,0,0)==[]
