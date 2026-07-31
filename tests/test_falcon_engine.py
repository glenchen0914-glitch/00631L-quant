import numpy as np
import pandas as pd

from src.falcon_engine import evaluate, market_gate, target_position


def sample_df(n=80):
    close = np.linspace(100, 112, n)
    df = pd.DataFrame({
        "open": close - 0.3,
        "high": close + 0.8,
        "low": close - 0.8,
        "close": close,
        "volume": np.linspace(1000, 850, n),
    })
    df["ma5"] = df.close.rolling(5).mean()
    df["ma10"] = df.close.rolling(10).mean()
    df["ma20"] = df.close.rolling(20).mean()
    df["atr14"] = 1.5
    df["macd_hist"] = np.linspace(-0.2, 0.5, n)
    df["rsi14"] = 60
    df["k"] = np.linspace(40, 65, n)
    df["d"] = np.linspace(42, 60, n)
    return df


def test_veto_caps_position():
    gate = market_gate(events=["CPI"], vix_level=18)
    assert gate.cap_pct == 20
    assert target_position(90, gate.cap_pct) == 20


def test_black_swan_blocks():
    assert market_gate(black_swan=True).cap_pct == 0


def test_gap_filter_and_step_position():
    r = evaluate(sample_df(), gap_pct=3.0)
    assert r["position"]["target_pct"] in (0, 20, 60)
    assert r["execution"]["wait_until"] == "09:15"
    assert r["position"]["target_pct"] <= r["gate"]["cap_pct"]


def test_atr_risk_is_dynamic():
    r = evaluate(sample_df())
    assert r["risk"]["initial_stop"] < sample_df().close.iloc[-1]
    assert r["risk"]["trailing_distance"] > 0
