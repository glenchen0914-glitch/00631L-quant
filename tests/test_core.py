import numpy as np,pandas as pd
from falcon.indicators import enrich
from falcon.config import load_settings
from falcon.engines import Orchestrator

def df():
    idx=pd.date_range("2025-01-01",periods=120,freq="B"); c=np.linspace(100,130,120)
    return enrich(pd.DataFrame({"Open":c-.5,"High":c+1,"Low":c-1,"Close":c,"Volume":np.ones(120)*1e6},index=idx))
def test_indicators():
    x=df()
    assert all(k in x for k in ["SMA60","MACD","K","D","ATR14","VOL_RATIO"])
def test_orchestrator():
    s=load_settings(); r=Orchestrator(s).run({k:df() for k in s.tickers})
    assert len(r.decisions)==2 and 0<=r.market.score<=100
