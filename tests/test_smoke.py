
from pathlib import Path
import sys, tempfile
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import types
if "yfinance" not in sys.modules:
    yf_stub = types.ModuleType("yfinance")
    def _offline_download(*args, **kwargs):
        raise RuntimeError("離線測試不呼叫 yfinance.download")
    yf_stub.download = _offline_download
    sys.modules["yfinance"] = yf_stub

import numpy as np
import pandas as pd

from src.config import Config
from src.pipeline import (
    build_features, tiered_entry_plan, _nearest_levels,
    bottom_progress_breakdown, make_decision, save_outputs
)

def synthetic_market_data(n=1200, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-01", periods=n)
    names = ["etf","twii","nasdaq","sox","sp500","vix","dxy","us10y","tsm_adr"]
    data = {}
    for i, name in enumerate(names):
        drift = 0.00035 if name != "vix" else 0.00005
        vol = 0.017 if name == "etf" else 0.012
        rets = rng.normal(drift, vol, n)
        close = (30 + i * 5) * np.exp(np.cumsum(rets))
        open_ = close * (1 + rng.normal(0, 0.003, n))
        high = np.maximum(open_, close) * (1 + rng.uniform(0.001, 0.012, n))
        low = np.minimum(open_, close) * (1 - rng.uniform(0.001, 0.012, n))
        volume = rng.integers(100_000, 2_000_000, n)
        data[name] = pd.DataFrame({
            "Open": open_, "High": high, "Low": low, "Close": close,
            "Adj Close": close, "Volume": volume
        }, index=dates)
    return data

def fake_board():
    rows = []
    for i in range(5):
        rows.append({
            "name": f"S{i+1:05d}", "week_k_max": 40, "rsi_max": 45,
            "require_k_cross": False, "require_macd_improve": False,
            "require_close_ma20": False, "require_twii_ma20": False,
            "stop_loss": 0.07, "take_profit": 0.15, "max_hold": 20,
            "score": 5.0 - i * 0.1,
            "trades_train": 30, "win_rate_train": 0.55,
            "avg_return_train": 0.02, "profit_factor_train": 1.8,
            "max_drawdown_train": -0.18, "cagr_train": 0.12,
            "total_return_train": 0.60,
            "trades_test": 12, "win_rate_test": 0.58,
            "avg_return_test": 0.018, "profit_factor_test": 1.7,
            "max_drawdown_test": -0.15, "cagr_test": 0.10,
            "total_return_test": 0.25,
        })
    return pd.DataFrame(rows)

data = synthetic_market_data()
df = build_features(data)
assert len(df) > 500

manual_missing = {
    "foreign_futures_net_oi": None, "margin_change": None,
    "margin_maintenance_ratio": None, "tx_night_change_pct": None,
    "event_risk_score": None, "event_note": "",
}
breakdown = bottom_progress_breakdown(df, manual_missing)
assert breakdown["items"]["融資"] is None
assert breakdown["data_status"]["融資"] == "資料未提供"

levels = _nearest_levels(df)
plan = tiered_entry_plan(df, levels, "觀察")
assert plan["first"] > plan["second"] > plan["third"] > plan["stop"] > 0
assert plan["first"] - plan["second"] >= plan["min_gap"] * 0.99
assert plan["second"] - plan["third"] >= plan["min_gap"] * 0.99

board = fake_board()
decision = make_decision(df, board, manual_missing)
assert decision["version"] == "V6.0 Final"
assert decision["data_status"]["融資"] == "資料未提供"
assert decision["entry_plan"]["first"] > decision["entry_plan"]["second"]
assert decision["entry_plan"]["second"] > decision["entry_plan"]["third"]
assert decision["entry_plan"]["third"] > decision["entry_plan"]["stop"]

with tempfile.TemporaryDirectory() as td:
    cfg = Config(reports_dir=str(Path(td) / "reports"), db_path=str(Path(td) / "market.db"))
    save_outputs(df, board, {}, decision, cfg)
    report_dir = Path(cfg.reports_dir)
    for filename in ["daily_decision.json","dashboard.html","strategy_leaderboard.csv","wave_tracking.csv"]:
        assert (report_dir / filename).exists()
    html = (report_dir / "dashboard.html").read_text(encoding="utf-8")
    assert "資料未提供" in html
    assert "V6.0 Final" in html

print("PASS: 離線煙霧測試")
print({
    "rows": len(df),
    "entry_plan": decision["entry_plan"],
    "margin_status": decision["data_status"]["融資"],
    "market_regime": decision["market_regime"],
    "ml_signal": decision["ml_signal"],
})
