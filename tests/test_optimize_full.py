
from pathlib import Path
import sys, types
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

if "yfinance" not in sys.modules:
    yf=types.ModuleType("yfinance")
    yf.download=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("offline"))
    sys.modules["yfinance"]=yf

import numpy as np
import pandas as pd
from src.config import Config
from src.pipeline import build_features, optimize

def synthetic(n=900,seed=7):
    rng=np.random.default_rng(seed)
    dates=pd.bdate_range("2022-01-01",periods=n)
    names=["etf","twii","nasdaq","sox","sp500","vix","dxy","us10y","tsm_adr"]
    out={}
    for i,name in enumerate(names):
        drift=0.00025 if name!="vix" else -0.00005
        close=(25+i*4)*np.exp(np.cumsum(rng.normal(drift,0.015,n)))
        op=close*(1+rng.normal(0,0.003,n))
        hi=np.maximum(op,close)*(1+rng.uniform(.001,.01,n))
        lo=np.minimum(op,close)*(1-rng.uniform(.001,.01,n))
        out[name]=pd.DataFrame({
            "Open":op,"High":hi,"Low":lo,"Close":close,
            "Adj Close":close,"Volume":rng.integers(100000,1000000,n)
        },index=dates)
    return out

df=build_features(synthetic())
cfg=Config(top_n=10,min_total_trades=4,min_test_trades=2)
board,trades=optimize(df,cfg)
assert not board.empty
assert len(board)<=10
assert "final_score" in board.columns
assert "wf_windows" in board.columns
assert set(board["name"]).issubset(trades.keys())
print("PASS: 完整策略產生、回測、候選排序與Walk-forward")
print(board[["name","description","trades_test","profit_factor_test","wf_windows","final_score"]].head())
