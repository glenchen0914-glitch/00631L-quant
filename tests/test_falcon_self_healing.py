from __future__ import annotations

from pathlib import Path
import tempfile

import pandas as pd

import src.falcon_data as fd


def sample_features(rows: int = 260) -> pd.DataFrame:
    idx = pd.date_range("2025-01-01", periods=rows, freq="B")
    close = pd.Series(range(100, 100 + rows), index=idx, dtype=float)
    return pd.DataFrame({
        "open": close - 0.3,
        "high": close + 1.0,
        "low": close - 1.0,
        "close": close,
        "volume": 1000.0,
        "ma5": close.rolling(5).mean(),
        "ma10": close.rolling(10).mean(),
        "ma20": close.rolling(20).mean(),
        "atr14": 2.0,
        "rsi14": 55.0,
        "macd_hist": 0.5,
    }).dropna()


def test_existing_valid_file_is_loaded(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "features.parquet"
        path.write_bytes(b"mock parquet")
        frame = sample_features()
        monkeypatch.setitem(fd.ASSETS, "TEST", {"features_path": str(path)})
        monkeypatch.setattr(fd.pd, "read_parquet", lambda p: frame)
        result = fd.ensure_features("TEST")
        assert len(result) >= 30


def test_missing_file_triggers_rebuild(monkeypatch):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "features.parquet"
        monkeypatch.setitem(fd.ASSETS, "TEST", {"features_path": str(path)})
        rebuilt = sample_features()
        monkeypatch.setattr(fd, "rebuild_features", lambda asset: rebuilt)
        result = fd.ensure_features("TEST")
        assert len(result) == len(rebuilt)
