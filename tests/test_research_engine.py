from __future__ import annotations

import numpy as np
import pandas as pd

from src.research_engine import analyze_similar_history


def synthetic_features(rows: int = 520) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.bdate_range("2024-01-01", periods=rows)
    returns = rng.normal(0.0005, 0.015, rows)
    close = 30 * np.exp(np.cumsum(returns))
    open_ = close * (1 + rng.normal(0, 0.004, rows))
    high = np.maximum(open_, close) * (1 + rng.uniform(0.002, 0.015, rows))
    low = np.minimum(open_, close) * (1 - rng.uniform(0.002, 0.015, rows))
    volume = rng.integers(1_000_000, 6_000_000, rows).astype(float)
    df = pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=idx)
    df["ma5"] = df["close"].rolling(5).mean()
    df["ma10"] = df["close"].rolling(10).mean()
    df["ma20"] = df["close"].rolling(20).mean()
    tr = pd.concat([(df.high-df.low), (df.high-df.close.shift()).abs(), (df.low-df.close.shift()).abs()], axis=1).max(axis=1)
    df["atr14"] = tr.rolling(14).mean()
    delta = df.close.diff(); up = delta.clip(lower=0).rolling(14).mean(); down = (-delta.clip(upper=0)).rolling(14).mean()
    df["rsi14"] = 100 - 100 / (1 + up / down.replace(0, np.nan))
    ema12 = df.close.ewm(span=12, adjust=False).mean(); ema26 = df.close.ewm(span=26, adjust=False).mean()
    macd = ema12-ema26; signal = macd.ewm(span=9, adjust=False).mean(); df["macd_hist"] = macd-signal
    ll = df.low.rolling(9).min(); hh = df.high.rolling(9).max(); rsv = (df.close-ll)/(hh-ll)*100
    df["k"] = rsv.ewm(alpha=1/3, adjust=False).mean(); df["d"] = df.k.ewm(alpha=1/3, adjust=False).mean()
    return df.dropna()


def test_research_has_honest_evidence_and_oos():
    report = analyze_similar_history(synthetic_features(), asset_code="00631L", neighbors=50)
    assert report["research_version"] == "Falcon Research v2.0.1"
    assert report["horizons"]["5"]["sample_count"] >= 30
    assert 0 <= report["horizons"]["5"]["win_rate_pct"] <= 100
    assert report["validation_5d"]["oos_cases"] > 0
    assert len(report["top_similar_dates"]) == 10
    assert "lookahead_control" in report


def test_research_rejects_short_history():
    try:
        analyze_similar_history(synthetic_features(150), asset_code="00631L")
    except ValueError as exc:
        assert "不足180筆" in str(exc)
    else:
        raise AssertionError("short history should fail")
