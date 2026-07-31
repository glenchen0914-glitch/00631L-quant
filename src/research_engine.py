from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import json
import math

import numpy as np
import pandas as pd


FEATURE_COLUMNS = (
    "ma20_bias",
    "ma5_ma10_spread",
    "ma10_ma20_spread",
    "macd_atr",
    "rsi_scaled",
    "kd_spread",
    "support_distance_atr",
    "volume_ratio",
    "range_atr",
)


@dataclass(frozen=True)
class HorizonStats:
    horizon_days: int
    sample_count: int
    win_count: int
    win_rate_pct: float | None
    average_return_pct: float | None
    median_return_pct: float | None
    expected_return_after_cost_pct: float | None
    average_mae_pct: float | None
    worst_mae_pct: float | None
    average_mfe_pct: float | None
    return_ci95_low_pct: float | None
    return_ci95_high_pct: float | None


@dataclass(frozen=True)
class ValidationStats:
    oos_cases: int
    directional_accuracy_pct: float | None
    mean_absolute_error_pct: float | None
    prediction_return_correlation: float | None


def _safe_div(a: pd.Series, b: pd.Series, default: float = 0.0) -> pd.Series:
    out = a.astype(float).div(b.astype(float).replace(0, np.nan))
    return out.replace([np.inf, -np.inf], np.nan).fillna(default)


def _feature_frame(df: pd.DataFrame) -> pd.DataFrame:
    required = {"open", "high", "low", "close", "volume", "ma5", "ma10", "ma20", "atr14", "rsi14", "macd_hist"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Research Engine缺少欄位：{', '.join(missing)}")

    x = pd.DataFrame(index=df.index)
    atr = df["atr14"].astype(float).clip(lower=df["close"].astype(float) * 0.003)
    x["ma20_bias"] = _safe_div(df["close"] - df["ma20"], atr)
    x["ma5_ma10_spread"] = _safe_div(df["ma5"] - df["ma10"], atr)
    x["ma10_ma20_spread"] = _safe_div(df["ma10"] - df["ma20"], atr)
    x["macd_atr"] = _safe_div(df["macd_hist"], atr)
    x["rsi_scaled"] = (df["rsi14"].astype(float) - 50.0) / 20.0
    k_col = "k" if "k" in df.columns else "day_k" if "day_k" in df.columns else None
    d_col = "d" if "d" in df.columns else "day_d" if "day_d" in df.columns else None
    if k_col and d_col:
        x["kd_spread"] = (df[k_col].astype(float) - df[d_col].astype(float)) / 20.0
    else:
        x["kd_spread"] = 0.0
    supports = pd.concat([df["ma5"], df["ma10"], df["ma20"]], axis=1)
    x["support_distance_atr"] = supports.sub(df["close"], axis=0).abs().min(axis=1).div(atr)
    vol_ma10 = df["volume"].astype(float).rolling(10).mean()
    x["volume_ratio"] = _safe_div(df["volume"], vol_ma10, default=1.0).clip(0, 5)
    x["range_atr"] = _safe_div(df["high"] - df["low"], atr).clip(0, 6)
    return x.replace([np.inf, -np.inf], np.nan)


def _future_outcomes(df: pd.DataFrame, horizon: int) -> pd.DataFrame:
    close = df["close"].astype(float)
    ret = close.shift(-horizon).div(close).sub(1.0)
    future_lows = pd.concat([df["low"].shift(-i) for i in range(1, horizon + 1)], axis=1)
    future_highs = pd.concat([df["high"].shift(-i) for i in range(1, horizon + 1)], axis=1)
    mae = future_lows.min(axis=1).div(close).sub(1.0)
    mfe = future_highs.max(axis=1).div(close).sub(1.0)
    return pd.DataFrame({"future_return": ret, "mae": mae, "mfe": mfe}, index=df.index)


def _standardized_distances(history: pd.DataFrame, target: pd.Series) -> pd.Series:
    median = history.median(axis=0)
    scale = (history.quantile(0.75) - history.quantile(0.25)).replace(0, np.nan)
    scale = scale.fillna(history.std(ddof=0)).replace(0, 1.0).fillna(1.0)
    hz = history.sub(median).div(scale)
    tz = target.sub(median).div(scale)
    return hz.sub(tz, axis=1).pow(2).mean(axis=1).pow(0.5)


def _bootstrap_ci(values: np.ndarray, *, seed: int = 631, iterations: int = 1000) -> tuple[float | None, float | None]:
    values = values[np.isfinite(values)]
    if len(values) < 20:
        return None, None
    rng = np.random.default_rng(seed)
    means = np.empty(iterations)
    for i in range(iterations):
        means[i] = rng.choice(values, size=len(values), replace=True).mean()
    low, high = np.quantile(means, [0.025, 0.975])
    return float(low), float(high)


def _round_pct(value: float | None) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value * 100.0, 2)


def _horizon_stats(matches: pd.DataFrame, horizon: int, cost_rate: float) -> HorizonStats:
    vals = matches["future_return"].dropna().to_numpy(dtype=float)
    if len(vals) == 0:
        return HorizonStats(horizon, 0, 0, None, None, None, None, None, None, None, None, None)
    wins = int((vals > cost_rate).sum())
    low, high = _bootstrap_ci(vals)
    return HorizonStats(
        horizon_days=horizon,
        sample_count=int(len(vals)),
        win_count=wins,
        win_rate_pct=round(wins / len(vals) * 100.0, 1),
        average_return_pct=_round_pct(float(np.mean(vals))),
        median_return_pct=_round_pct(float(np.median(vals))),
        expected_return_after_cost_pct=_round_pct(float(np.mean(vals) - cost_rate)),
        average_mae_pct=_round_pct(float(matches["mae"].mean())),
        worst_mae_pct=_round_pct(float(matches["mae"].min())),
        average_mfe_pct=_round_pct(float(matches["mfe"].mean())),
        return_ci95_low_pct=_round_pct(low),
        return_ci95_high_pct=_round_pct(high),
    )


def _walk_forward_validation(features: pd.DataFrame, outcomes: pd.DataFrame, *, horizon: int, neighbors: int) -> ValidationStats:
    joined = features.join(outcomes).dropna()
    if len(joined) < 160:
        return ValidationStats(0, None, None, None)
    start = max(100, int(len(joined) * 0.8))
    predictions: list[float] = []
    actuals: list[float] = []
    for i in range(start, len(joined)):
        train = joined.iloc[:i]
        target = joined.iloc[i][list(FEATURE_COLUMNS)]
        d = _standardized_distances(train[list(FEATURE_COLUMNS)], target)
        k = min(neighbors, len(d))
        nearest = train.loc[d.nsmallest(k).index]
        weights = 1.0 / (d.loc[nearest.index].to_numpy() + 0.05)
        pred = float(np.average(nearest["future_return"].to_numpy(), weights=weights))
        predictions.append(pred)
        actuals.append(float(joined.iloc[i]["future_return"]))
    if not predictions:
        return ValidationStats(0, None, None, None)
    p = np.asarray(predictions)
    a = np.asarray(actuals)
    accuracy = float((np.sign(p) == np.sign(a)).mean() * 100.0)
    mae = float(np.mean(np.abs(p - a)) * 100.0)
    corr = float(np.corrcoef(p, a)[0, 1]) if len(p) >= 3 and np.std(p) > 0 and np.std(a) > 0 else None
    return ValidationStats(len(p), round(accuracy, 1), round(mae, 2), None if corr is None else round(corr, 3))


def analyze_similar_history(
    df: pd.DataFrame,
    *,
    asset_code: str,
    horizons: tuple[int, ...] = (3, 5, 10),
    neighbors: int = 60,
    estimated_roundtrip_cost_pct: float = 0.20,
) -> dict[str, Any]:
    """Analyze historical states similar to the latest row without using future data.

    This is evidence generation, not a promise of future performance. The current
    state is compared only with earlier dates; future returns are used solely as
    labels for those earlier historical dates.
    """
    if len(df) < 180:
        raise ValueError(f"{asset_code} 歷史資料不足180筆，無法建立可靠研究樣本")
    df = df.sort_index().copy()
    features = _feature_frame(df)
    current_features = features.iloc[-1]
    max_h = max(horizons)
    eligible_features = features.iloc[:-max_h].dropna()
    if len(eligible_features) < 100:
        raise ValueError(f"{asset_code} 有效歷史特徵不足100筆")
    distances = _standardized_distances(eligible_features[list(FEATURE_COLUMNS)], current_features[list(FEATURE_COLUMNS)])
    k = min(max(30, neighbors), len(distances))
    nearest_idx = distances.nsmallest(k).index
    cost_rate = estimated_roundtrip_cost_pct / 100.0

    horizon_results: dict[str, Any] = {}
    primary_matches: pd.DataFrame | None = None
    for horizon in horizons:
        outcomes = _future_outcomes(df, horizon)
        matches = outcomes.loc[nearest_idx].copy()
        matches["distance"] = distances.loc[nearest_idx]
        matches = matches.dropna().sort_values("distance")
        if horizon == 5:
            primary_matches = matches
        horizon_results[str(horizon)] = asdict(_horizon_stats(matches, horizon, cost_rate))

    primary_outcomes = _future_outcomes(df, 5)
    validation = _walk_forward_validation(features.iloc[:-5], primary_outcomes.iloc[:-5], horizon=5, neighbors=min(40, k))
    five = horizon_results.get("5", {})
    sample = int(five.get("sample_count") or 0)
    ci_low = five.get("return_ci95_low_pct")
    oos_cases = validation.oos_cases
    if sample < 30:
        confidence = "資料不足"
    elif sample < 60 or oos_cases < 30:
        confidence = "有限"
    elif ci_low is not None and ci_low > 0 and (validation.directional_accuracy_pct or 0) >= 52:
        confidence = "中等"
    else:
        confidence = "審慎"

    top_matches: list[dict[str, Any]] = []
    if primary_matches is not None:
        for idx, row in primary_matches.head(10).iterrows():
            top_matches.append({
                "date": str(pd.Timestamp(idx).date()),
                "similarity_pct": round(max(0.0, 100.0 / (1.0 + float(row["distance"]))), 1),
                "return_5d_pct": _round_pct(float(row["future_return"])),
                "mae_5d_pct": _round_pct(float(row["mae"])),
                "mfe_5d_pct": _round_pct(float(row["mfe"])),
            })

    return {
        "research_version": "Falcon Research v2.0.0",
        "asset_code": asset_code,
        "data_asof": str(pd.Timestamp(df.index[-1]).date()),
        "method": "robust-scaled nearest historical states + expanding walk-forward validation",
        "lookahead_control": "current state only matches dates strictly before the maximum forward horizon",
        "estimated_roundtrip_cost_pct": estimated_roundtrip_cost_pct,
        "neighbor_count": k,
        "feature_columns": list(FEATURE_COLUMNS),
        "confidence": confidence,
        "horizons": horizon_results,
        "validation_5d": asdict(validation),
        "top_similar_dates": top_matches,
        "limitations": [
            "歷史相似不代表未來必然重演",
            "目前使用日線資料，尚未納入盤中成交結構與即時新聞",
            "勝率門檻已扣除設定的估計往返成本，但未包含個人實際滑價與費率",
            "正式提高倉位前仍須通過Gate、執行與風控規則",
        ],
    }


def save_research_report(report: dict[str, Any], json_path: str | Path, csv_path: str | Path) -> None:
    jp = Path(json_path)
    cp = Path(csv_path)
    jp.parent.mkdir(parents=True, exist_ok=True)
    cp.parent.mkdir(parents=True, exist_ok=True)
    jp.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = []
    for horizon, stats in report.get("horizons", {}).items():
        rows.append({"asset_code": report.get("asset_code"), "data_asof": report.get("data_asof"), **stats})
    pd.DataFrame(rows).to_csv(cp, index=False)
