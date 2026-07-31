from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Any, Iterable
import json
import math

import numpy as np
import pandas as pd

POSITION_STEPS = (0, 20, 60, 100)


@dataclass(frozen=True)
class GateResult:
    cap_pct: int
    level: str
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class ScoreResult:
    trend: int
    pullback: int
    momentum: int
    total: int
    reasons: tuple[str, ...]


@dataclass(frozen=True)
class RiskPlan:
    atr: float
    initial_stop: float
    trailing_distance: float
    first_take_profit: float
    risk_per_unit: float
    confirmation_rule: str


def _finite(value: Any, default: float = 0.0) -> float:
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default


def _last(df: pd.DataFrame, col: str, default: float = 0.0) -> float:
    return _finite(df[col].iloc[-1], default) if col in df and len(df) else default


def _previous(df: pd.DataFrame, col: str, default: float = 0.0) -> float:
    return _finite(df[col].iloc[-2], default) if col in df and len(df) >= 2 else default


def market_gate(
    *,
    events: Iterable[str] = (),
    vix_level: float | None = None,
    vix_change_pct: float | None = None,
    index_ma20_bias_pct: float | None = None,
    consecutive_up_days: int = 0,
    gap_pct: float | None = None,
    black_swan: bool = False,
) -> GateResult:
    """Hard risk gate. It limits size; it never adds bullish points."""
    cap = 100
    reasons: list[str] = []
    event_set = {str(x).strip().upper() for x in events if str(x).strip()}
    major = {"FOMC", "CPI", "PPI", "NFP", "NONFARM", "TSMC_EARNINGS", "台積電法說"}

    if black_swan:
        return GateResult(0, "封鎖", ("黑天鵝／重大突發事件",))
    if event_set & major:
        cap = min(cap, 20)
        reasons.append("重大事件日，倉位上限20%")
    if vix_level is not None and _finite(vix_level) >= 30:
        cap = min(cap, 0)
        reasons.append("VIX達30以上，禁止新建多單")
    elif (vix_level is not None and _finite(vix_level) >= 22) or (
        vix_change_pct is not None and _finite(vix_change_pct) > 8
    ):
        cap = min(cap, 20)
        reasons.append("VIX越過22或單日急升逾8%")
    if index_ma20_bias_pct is not None and _finite(index_ma20_bias_pct) > 5:
        cap = min(cap, 20)
        reasons.append("大盤20MA正乖離超過5%，嚴重過熱")
    if consecutive_up_days >= 4:
        cap = min(cap, 60)
        reasons.append("標的連漲4日以上，限制追價倉位")
    if gap_pct is not None and _finite(gap_pct) > 4:
        cap = min(cap, 20)
        reasons.append("預估／實際跳空超過4%")
    elif gap_pct is not None and _finite(gap_pct) > 2.5:
        cap = min(cap, 60)
        reasons.append("跳空超過2.5%，需等09:15後確認")

    level = {0: "封鎖", 20: "高度防禦", 60: "限制", 100: "正常"}[cap]
    if not reasons:
        reasons.append("未觸發硬性風險門檻")
    return GateResult(cap, level, tuple(reasons))


def _score_band(value: float, cuts: tuple[float, ...], points: tuple[int, ...]) -> int:
    for cut, point in zip(cuts, points):
        if value >= cut:
            return point
    return 0


def score_features(df: pd.DataFrame) -> ScoreResult:
    """Three orthogonal buckets: trend 40, pullback quality 40, momentum 20."""
    if len(df) < 30:
        return ScoreResult(0, 0, 0, 0, ("資料不足30筆",))

    close = _last(df, "close")
    ma5, ma10, ma20 = (_last(df, x) for x in ("ma5", "ma10", "ma20"))
    atr = max(_last(df, "atr14", close * 0.02), close * 0.005)
    vol = _last(df, "volume")
    vol_ma10 = _finite(df["volume"].rolling(10).mean().iloc[-1], vol) if "volume" in df else vol
    macd = _last(df, "macd_hist")
    macd_prev = _previous(df, "macd_hist")
    rsi = _last(df, "rsi14", 50)
    k = _last(df, "k", _last(df, "day_k", 50))
    d = _last(df, "d", _last(df, "day_d", 50))
    k_prev = _previous(df, "k", _previous(df, "day_k", 50))
    d_prev = _previous(df, "d", _previous(df, "day_d", 50))

    reasons: list[str] = []

    trend = 0
    if close > ma20: trend += 12; reasons.append("收盤站上20MA")
    if ma5 > ma10 > ma20: trend += 12; reasons.append("短中期均線多頭排列")
    elif ma5 > ma10: trend += 6; reasons.append("5MA高於10MA")
    if ma5 > _previous(df, "ma5", ma5): trend += 6; reasons.append("5MA向上")
    if macd > 0: trend += 6; reasons.append("MACD柱體為正")
    elif macd > macd_prev: trend += 3; reasons.append("MACD柱體改善")
    if 50 <= rsi <= 70: trend += 4; reasons.append("RSI位於健康多方區")
    trend = min(40, trend)

    pullback = 0
    # Distance to nearest support measured in ATR; reward controlled pullback, not extension.
    supports = [x for x in (ma5, ma10, ma20) if x > 0]
    distance_atr = min(abs(close - x) / atr for x in supports) if supports else 99
    if distance_atr <= 0.35: pullback += 15; reasons.append("價格貼近均線支撐")
    elif distance_atr <= 0.75: pullback += 9; reasons.append("價格接近支撐區")
    if vol_ma10 > 0 and vol / vol_ma10 < 0.90: pullback += 10; reasons.append("拉回量縮")
    if "high" in df and "low" in df:
        ranges = (df["high"] - df["low"]).astype(float)
        recent_range = _finite(ranges.iloc[-1])
        range_ma5 = _finite(ranges.rolling(5).mean().iloc[-1], recent_range)
        if recent_range < range_ma5 * 0.85: pullback += 8; reasons.append("日內波動收斂")
        lower_shadow = min(_last(df, "open", close), close) - _last(df, "low", close)
        body = abs(close - _last(df, "open", close))
        if lower_shadow > max(body, atr * 0.18): pullback += 7; reasons.append("出現有效下影線")
    pullback = min(40, pullback)

    momentum = 0
    if k > d and k_prev <= d_prev: momentum += 8; reasons.append("KD黃金交叉")
    elif k > d: momentum += 4; reasons.append("KD維持多方")
    if macd > macd_prev: momentum += 6; reasons.append("MACD動能增強")
    if len(df) >= 21:
        prior_high = _finite(df["high"].iloc[-21:-1].max()) if "high" in df else _finite(df["close"].iloc[-21:-1].max())
        if close > prior_high: momentum += 6; reasons.append("突破20日高點")
    momentum = min(20, momentum)

    total = int(trend + pullback + momentum)
    return ScoreResult(trend, pullback, momentum, total, tuple(reasons))


def target_position(score: int, gate_cap: int, current_position: int = 0) -> int:
    raw = 0 if score < 40 else 20 if score < 60 else 60 if score < 75 else 100
    target = min(raw, gate_cap)
    # Hysteresis: do not churn one step down unless score is clearly below the prior threshold.
    if current_position >= 60 and target == 20 and score >= 55:
        target = min(60, gate_cap)
    if current_position == 100 and target == 60 and score >= 70:
        target = min(100, gate_cap)
    return int(target)


def risk_plan(df: pd.DataFrame, entry_price: float | None = None) -> RiskPlan:
    close = _last(df, "close")
    entry = _finite(entry_price, close) or close
    atr = max(_last(df, "atr14", close * 0.02), close * 0.005)
    stop = max(0.01, entry - 1.5 * atr)
    trail = 2.0 * atr
    first_tp = entry + 2.0 * atr
    return RiskPlan(
        atr=round(atr, 4),
        initial_stop=round(stop, 4),
        trailing_distance=round(trail, 4),
        first_take_profit=round(first_tp, 4),
        risk_per_unit=round(entry - stop, 4),
        confirmation_rule="停損以收盤確認為主；若盤中跌破2ATR或重大突發事件則立即防禦",
    )


def execution_rules(*, gap_pct: float | None, score: int, gate_cap: int) -> dict[str, Any]:
    gap = _finite(gap_pct)
    wait_until = None
    chase = "允許依買點分批"
    if gap > 4:
        chase = "禁止追價，僅觀察拉回止穩"
        wait_until = "09:30"
    elif gap > 2.5:
        chase = "前15分鐘禁止追價，09:15後須守住開盤低點"
        wait_until = "09:15"
    elif gap > 1.5:
        chase = "不以市價追高，等待第一次回測"
        wait_until = "09:10"
    return {
        "gap_pct": gap,
        "chase_rule": chase,
        "wait_until": wait_until,
        "new_position_allowed": gate_cap > 0 and score >= 40,
    }


def evaluate(
    df: pd.DataFrame,
    *,
    events: Iterable[str] = (),
    vix_level: float | None = None,
    vix_change_pct: float | None = None,
    index_ma20_bias_pct: float | None = None,
    consecutive_up_days: int = 0,
    gap_pct: float | None = None,
    black_swan: bool = False,
    current_position: int = 0,
) -> dict[str, Any]:
    gate = market_gate(
        events=events, vix_level=vix_level, vix_change_pct=vix_change_pct,
        index_ma20_bias_pct=index_ma20_bias_pct,
        consecutive_up_days=consecutive_up_days, gap_pct=gap_pct,
        black_swan=black_swan,
    )
    scores = score_features(df)
    target = target_position(scores.total, gate.cap_pct, current_position)
    risk = risk_plan(df)
    execution = execution_rules(gap_pct=gap_pct, score=scores.total, gate_cap=gate.cap_pct)
    action = (
        "禁止新建倉位" if gate.cap_pct == 0 else
        "維持空手觀察" if target == 0 else
        f"階梯式配置至{target}%"
    )
    return {
        "engine_version": "Falcon v1.0",
        "generated_for": str(date.today()),
        "gate": asdict(gate),
        "scores": asdict(scores),
        "position": {"current_pct": int(current_position), "target_pct": target, "steps": list(POSITION_STEPS)},
        "risk": asdict(risk),
        "execution": execution,
        "action": action,
    }


def save_report(report: dict[str, Any], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
