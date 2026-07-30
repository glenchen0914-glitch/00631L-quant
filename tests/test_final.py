
from pathlib import Path
import sys, tempfile, types
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if "yfinance" not in sys.modules:
    yf_stub = types.ModuleType("yfinance")
    yf_stub.download = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
    sys.modules["yfinance"] = yf_stub

import numpy as np
import pandas as pd
from src.config import Config
from src.pipeline import (
    build_features, _nearest_levels, tiered_entry_plan,
    bottom_progress_breakdown, make_decision, save_outputs,
    data_quality_report
)

def synthetic_market_data(n=1200, seed=42, regime="mixed", missing=None):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=n)
    names = ["etf","twii","nasdaq","sox","sp500","vix","dxy","us10y","tsm_adr"]
    data = {}
    missing = set(missing or [])
    for i, name in enumerate(names):
        if name in missing:
            continue
        drift_map = {"bull":0.0008,"bear":-0.0006,"flat":0.0,"crash":-0.0015,"mixed":0.0002}
        drift = drift_map[regime]
        if name == "vix":
            drift = -drift * 0.4
        vol = 0.018 if name == "etf" else 0.013
        if regime == "crash": vol *= 1.8
        rets = rng.normal(drift, vol, n)
        close = (30+i*5)*np.exp(np.cumsum(rets))
        op = close*(1+rng.normal(0,0.003,n))
        high=np.maximum(op,close)*(1+rng.uniform(0.001,0.012,n))
        low=np.minimum(op,close)*(1-rng.uniform(0.001,0.012,n))
        data[name]=pd.DataFrame({"Open":op,"High":high,"Low":low,"Close":close,"Adj Close":close,"Volume":rng.integers(100000,2000000,n)},index=dates)
    return data

def fake_board():
    rows=[]
    for i in range(5):
        rows.append({
            "name":f"S{i+1:05d}","week_k_max":40,"rsi_max":45,
            "require_k_cross":False,"require_macd_improve":False,
            "require_close_ma20":False,"require_twii_ma20":False,
            "stop_loss":0.07,"take_profit":0.15,"max_hold":20,"score":5-i*.1,
            "description":"測試策略","wf_windows":4,"wf_positive_windows":3,"wf_median_pf":1.4,"wf_median_return":0.08,
            "trades_train":30,"win_rate_train":.55,"avg_return_train":.02,"profit_factor_train":1.8,
            "max_drawdown_train":-.18,"cagr_train":.12,"total_return_train":.60,
            "trades_test":12,"win_rate_test":.58,"avg_return_test":.018,"profit_factor_test":1.7,
            "max_drawdown_test":-.15,"cagr_test":.10,"total_return_test":.25,
        })
    return pd.DataFrame(rows)

manual={"foreign_futures_net_oi":None,"margin_change":None,"margin_maintenance_ratio":None,"tx_night_change_pct":None,"event_risk_score":None,"event_note":""}
board=fake_board()

for regime in ["bull","bear","flat","crash"]:
    data=synthetic_market_data(regime=regime)
    df=build_features(data)
    quality=data_quality_report(data,{k:k for k in data})
    decision=make_decision(df,board,manual,quality)
    plan=decision["entry_plan"]
    assert plan["first"]>plan["second"]>plan["third"]>plan["stop"]>0
    assert decision["version"]=="V6.0 Final"
    assert "confidence_grade" in decision
    assert "decision_explanation" in decision
    assert decision["data_status"]["融資"]=="資料未提供"
    with tempfile.TemporaryDirectory() as td:
        cfg=Config(reports_dir=str(Path(td)/"reports"),db_path=str(Path(td)/"market.db"))
        save_outputs(df,board,{},decision,cfg)
        html=(Path(cfg.reports_dir)/"dashboard.html").read_text(encoding="utf-8")
        assert "V6.0 Final" in html
        assert "支持進場理由" in html
        assert "資料未提供" in html

# 缺少部分市場資料時仍能降級運作
partial=synthetic_market_data(missing=["vix","sox"])
df=build_features(partial)
quality=data_quality_report(partial,{k:k for k in ["etf","twii","nasdaq","sox","sp500","vix","dxy","us10y","tsm_adr"]})
decision=make_decision(df,board,manual,quality)
assert quality["score"]<100
assert decision["data_quality"]["score"]==quality["score"]

print("PASS: V6.0 Final 多情境離線驗收")
