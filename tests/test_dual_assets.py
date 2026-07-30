from pathlib import Path
import sys, types, tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "yfinance" not in sys.modules:
    yf = types.ModuleType("yfinance")
    yf.download = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
    sys.modules["yfinance"] = yf

import numpy as np
import pandas as pd
from src.config import Config
from src.pipeline import build_features
from src.assets import _fallback_board, _apply_asset_rules
from src.notify import build_line_message

def synthetic(n=260, seed=21):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2025-05-01", periods=n)
    out = {}
    for i, name in enumerate(["etf","twii","nasdaq","sox","sp500","vix","dxy","us10y","tsm_adr"]):
        drift = 0.0003 if name != "vix" else -0.00005
        close = (15+i*3)*np.exp(np.cumsum(rng.normal(drift,0.014,n)))
        op = close*(1+rng.normal(0,0.003,n))
        hi = np.maximum(op,close)*(1+rng.uniform(.001,.012,n))
        lo = np.minimum(op,close)*(1-rng.uniform(.001,.012,n))
        out[name] = pd.DataFrame({
            "Open":op,"High":hi,"Low":lo,"Close":close,
            "Adj Close":close,"Volume":rng.integers(100000,1000000,n)
        }, index=dates)
    return out

df = build_features(synthetic())
cfg = Config(min_total_trades=3,min_test_trades=1,top_n=10)
board, trades = _fallback_board(df,cfg,"00981A")
best = board.iloc[0]
decision = {
    "bottom_progress_pct": 55,
    "market_regime": {"score":52,"label":"中性","parts":{}},
    "ensemble_signal":{"vote_ratio":0.0},
    "model_consensus":{"probability":None,"models":[]},
    "decision_explanation":{"positive":[],"negative":[],"missing":[]},
    "confidence_grade":{"score":65,"grade":"B"},
    "backtest_confidence":{"note":"樣本有限","level":"低","score":10},
    "stage":"觀察","suggested_position_pct":0,"action":"不進場，維持0%",
    "data_date":str(df.index[-1].date()),"reference_close":float(df["close"].iloc[-1]),
    "entry_plan":{"first":10.0,"second":9.5,"third":9.0,"stop":8.5},
}
decision = _apply_asset_rules(decision,df,"00981A")
assert decision["asset_code"] == "00981A"
assert decision["analysis_type"] == "短線操作"
assert decision["confidence_grade"]["score"] <= 49
assert "00981A 每日決策" in build_line_message(decision)
assert decision["progress_label"] == "短線轉強進度"
print("PASS: 00981A短線規則、歷史降級與LINE格式")
