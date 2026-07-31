from pathlib import Path
import sys
import types

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "yfinance" not in sys.modules:
    yf = types.ModuleType("yfinance")
    yf.download = lambda *args, **kwargs: None
    sys.modules["yfinance"] = yf

from src.morning import score_market, build_market_message, build_line_message, _asset_premarket

raw = {
    "NASDAQ": {"change_pct": 1.2},
    "SOX": {"change_pct": 1.8},
    "S&P500": {"change_pct": 0.8},
    "Dow": {"change_pct": 0.4},
    "Russell2000": {"change_pct": 0.5},
    "TSM ADR": {"change_pct": 1.6},
    "VIX": {"change_pct": -4.0},
    "美元指數": {"change_pct": -0.2},
    "美債10年": {"change_pct": -0.5},
    "S&P期貨": {"change_pct": 0.3},
    "NASDAQ期貨": {"change_pct": 0.5},
}
base = score_market(raw)
market = {**base, "raw": raw}
assert market["score"] > 50
assert "盤前市場摘要" in build_market_message(market)

close = {
    "data_date": "2026-07-30",
    "action": "不進場，維持0%",
    "suggested_position_pct": 0,
    "bottom_progress_pct": 60,
    "reference_close": 28.38,
    "confidence_grade": {"grade": "D", "score": 30},
    "entry_plan": {"first": 27.7, "second": 26.64, "third": 25.57, "stop": 24.89},
}
report = _asset_premarket("00631L", close, market)
assert report["asset_code"] == "00631L"
assert "07:00盤前決策" in build_line_message(report)
assert report["suggested_position_pct"] in (0, 10)
print("PASS: 07:00盤前市場評分、雙標的訊息與風控")
