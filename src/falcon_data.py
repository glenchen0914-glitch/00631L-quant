from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd

from src.assets import ASSETS, _configure
from src.pipeline import build_db, build_features, download_all


class FeatureBuildError(RuntimeError):
    """Raised when Falcon cannot self-heal market features."""


def _is_usable(path: Path, minimum_rows: int = 30) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    try:
        df = pd.read_parquet(path)
    except Exception:
        return False
    required = {"open", "high", "low", "close", "volume", "ma5", "ma10", "ma20", "atr14", "rsi14", "macd_hist"}
    return len(df) >= minimum_rows and required.issubset(df.columns)


def rebuild_features(asset_code: str) -> pd.DataFrame:
    """Download raw data and rebuild the feature parquet for one asset."""
    if asset_code not in ASSETS:
        raise KeyError(f"未知標的：{asset_code}")
    spec = ASSETS[asset_code]
    cfg = _configure(asset_code)
    try:
        data = download_all(cfg)
        build_db(data, cfg)
        features = build_features(data)
    except Exception as exc:
        raise FeatureBuildError(f"{asset_code} 行情／指標自動重建失敗：{exc}") from exc
    if len(features) < 30:
        raise FeatureBuildError(f"{asset_code} 重建後只有 {len(features)} 筆有效資料，無法分析")
    path = Path(spec["features_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(path)
    print(f"✅ {asset_code} 特徵檔已自動重建：{path}（{len(features)}筆）")
    return features


def ensure_features(asset_code: str, *, force_refresh: bool = False) -> pd.DataFrame:
    """Load a valid feature file, or self-heal by rebuilding it.

    Morning and close workflows can call this independently. A missing, empty,
    unreadable, or schema-incomplete parquet never requires the prior workflow.
    """
    spec = ASSETS[asset_code]
    path = Path(spec["features_path"])
    if not force_refresh and _is_usable(path):
        try:
            return pd.read_parquet(path)
        except Exception:
            pass
    reason = "強制更新" if force_refresh else "缺檔、損壞或欄位不完整"
    print(f"⚠️ {asset_code} 特徵資料{reason}，啟動 Self-Healing")
    return rebuild_features(asset_code)
