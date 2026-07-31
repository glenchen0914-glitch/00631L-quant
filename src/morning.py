from __future__ import annotations

import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

TAIPEI = timezone(timedelta(hours=8))

OVERNIGHT = {
    "NASDAQ": "^IXIC",
    "SOX": "^SOX",
    "S&P500": "^GSPC",
    "Dow": "^DJI",
    "Russell2000": "^RUT",
    "TSM ADR": "TSM",
    "VIX": "^VIX",
    "美元指數": "DX-Y.NYB",
    "美債10年": "^TNX",
    "S&P期貨": "ES=F",
    "NASDAQ期貨": "NQ=F",
}

ASSET_REPORTS = {
    "00631L": Path("reports/daily_decision.json"),
    "00981A": Path("reports/00981A/daily_decision.json"),
}


def _download_return(ticker: str) -> dict[str, Any]:
    data = yf.download(
        ticker,
        period="10d",
        interval="1d",
        auto_adjust=False,
        progress=False,
        threads=False,
    )
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = [c[0] for c in data.columns]
    data = data.dropna(subset=["Close"])
    if len(data) < 2:
        return {"ticker": ticker, "status": "資料不足"}

    close = data["Close"].astype(float)
    last = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    change = last / prev - 1 if prev else 0.0
    return {
        "ticker": ticker,
        "status": "正常",
        "date": str(pd.Timestamp(data.index[-1]).date()),
        "close": last,
        "change_pct": change * 100,
    }


def collect_overnight() -> dict[str, dict[str, Any]]:
    result = {}
    for name, ticker in OVERNIGHT.items():
        try:
            result[name] = _download_return(ticker)
        except Exception as exc:
            result[name] = {"ticker": ticker, "status": f"失敗：{exc}"}
    return result


def _pct(data: dict[str, dict[str, Any]], key: str) -> float | None:
    item = data.get(key, {})
    value = item.get("change_pct")
    return float(value) if isinstance(value, (int, float)) and math.isfinite(value) else None


def score_market(data: dict[str, dict[str, Any]]) -> dict[str, Any]:
    score = 50.0
    details: list[str] = []
    weights = {
        "NASDAQ": 8,
        "SOX": 12,
        "S&P500": 6,
        "Dow": 3,
        "Russell2000": 3,
        "TSM ADR": 12,
        "S&P期貨": 5,
        "NASDAQ期貨": 7,
    }

    for key, weight in weights.items():
        ret = _pct(data, key)
        if ret is None:
            continue
        contribution = float(np.clip(ret / 1.5, -1, 1) * weight)
        score += contribution
        details.append(f"{key} {ret:+.2f}%")

    vix = _pct(data, "VIX")
    if vix is not None:
        score += float(np.clip(-vix / 8, -1, 1) * 10)
        details.append(f"VIX {vix:+.2f}%")

    dxy = _pct(data, "美元指數")
    if dxy is not None:
        score += float(np.clip(-dxy / 1.0, -1, 1) * 5)
        details.append(f"美元 {dxy:+.2f}%")

    us10y = _pct(data, "美債10年")
    if us10y is not None:
        score += float(np.clip(-us10y / 2.5, -1, 1) * 5)
        details.append(f"美債10年 {us10y:+.2f}%")

    score = int(round(np.clip(score, 0, 100)))
    if score >= 70:
        label = "偏多"
    elif score >= 58:
        label = "中性偏多"
    elif score >= 43:
        label = "中性"
    elif score >= 30:
        label = "中性偏空"
    else:
        label = "偏空"

    return {"score": score, "label": label, "details": details}


def _load_close_decision(asset: str) -> dict[str, Any]:
    path = ASSET_REPORTS[asset]
    if not path.exists():
        raise FileNotFoundError(f"找不到昨日收盤決策：{path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _asset_premarket(asset: str, close_decision: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    market_score = int(market["score"])
    close_action = str(close_decision.get("action", "觀察"))
    close_position = int(close_decision.get("suggested_position_pct", 0))
    confidence = close_decision.get("confidence_grade", {})
    plan = close_decision.get("entry_plan", {})
    progress = int(close_decision.get("bottom_progress_pct", 0))

    tsm = _pct(market["raw"], "TSM ADR") or 0.0
    sox = _pct(market["raw"], "SOX") or 0.0
    nqf = _pct(market["raw"], "NASDAQ期貨") or 0.0

    adjustment = 0
    if asset == "00631L":
        adjustment = int(round((market_score - 50) * 0.45))
        if sox > 1:
            adjustment += 4
        if nqf < -1:
            adjustment -= 5
    else:
        adjustment = int(round((market_score - 50) * 0.35))
        if tsm > 1:
            adjustment += 6
        if sox > 1:
            adjustment += 4
        if tsm < -1:
            adjustment -= 6

    premarket_score = int(np.clip(progress + adjustment, 0, 100))

    if market_score < 35:
        instruction = "盤前環境偏空，不追價；等待第一筆價位與開盤止穩"
        suggested = 0
    elif close_position > 0 and market_score >= 55:
        instruction = f"延續收盤策略，最多維持{close_position}%；開高不追"
        suggested = close_position
    elif premarket_score >= 70 and market_score >= 58:
        instruction = "盤前條件改善，可等待開盤15～30分鐘確認後小量試單"
        suggested = min(10, max(close_position, 10))
    elif premarket_score >= 50:
        instruction = "接近觀察區，等待拉回與量價確認，不預掛追價單"
        suggested = 0
    else:
        instruction = "條件不足，今日以觀察為主"
        suggested = 0

    if market_score >= 65:
        open_bias = "偏多開出機率較高"
    elif market_score <= 35:
        open_bias = "偏空開出機率較高"
    else:
        open_bias = "開盤方向不明，需等待現貨確認"

    return {
        "asset_code": asset,
        "data_date": close_decision.get("data_date"),
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "close_action": close_action,
        "premarket_action": instruction,
        "suggested_position_pct": suggested,
        "premarket_score": premarket_score,
        "open_bias": open_bias,
        "reference_close": close_decision.get("reference_close"),
        "entry_plan": plan,
        "close_confidence": confidence,
        "market_score": market_score,
        "market_label": market["label"],
        "warnings": [
            "盤前報告使用前一交易日收盤與隔夜市場資料，不能取代開盤後量價確認",
            "GitHub公開資料源未納入正式台指期夜盤，期貨方向以美股期貨作為替代參考",
        ],
    }


def build_line_message(report: dict[str, Any]) -> str:
    plan = report.get("entry_plan", {})
    lines = [
        f"{report['asset_code']} 07:00盤前決策",
        f"基準資料日：{report.get('data_date', '-')}",
        "",
        f"盤前結論：{report['premarket_action']}",
        f"建議持股：{report['suggested_position_pct']}%",
        f"盤前分數：{report['premarket_score']}/100",
        f"隔夜環境：{report['market_label']} {report['market_score']}/100",
        f"預估開盤：{report['open_bias']}",
        f"參考收盤：{float(report.get('reference_close') or 0):.2f}",
        "",
        "今日價位：",
        f"第一筆 {float(plan.get('first') or 0):.2f}",
        f"第二筆 {float(plan.get('second') or 0):.2f}",
        f"第三筆 {float(plan.get('third') or 0):.2f}",
        f"防守線 {float(plan.get('stop') or 0):.2f}",
        "",
        "提醒：開盤後至少等待15分鐘確認量價，開高不追。",
    ]
    return "\n".join(lines)


def build_market_message(market: dict[str, Any]) -> str:
    raw = market["raw"]
    keys = ["NASDAQ", "SOX", "S&P500", "TSM ADR", "VIX", "美元指數", "美債10年", "NASDAQ期貨"]
    lines = [
        "07:00 盤前市場摘要",
        f"整體環境：{market['label']} {market['score']}/100",
        "",
    ]
    for key in keys:
        ret = _pct(raw, key)
        if ret is not None:
            lines.append(f"{key}：{ret:+.2f}%")
        else:
            lines.append(f"{key}：資料不足")
    lines += [
        "",
        "注意：盤前市場分數是方向性參考，不代表台股開盤必然同向。",
    ]
    return "\n".join(lines)


def run_morning() -> dict[str, Any]:
    raw = collect_overnight()
    market_base = score_market(raw)
    market = {**market_base, "raw": raw}

    reports = {}
    for asset in ("00631L", "00981A"):
        close_decision = _load_close_decision(asset)
        reports[asset] = _asset_premarket(asset, close_decision, market)

    output = {
        "generated_at": datetime.now(TAIPEI).isoformat(timespec="minutes"),
        "market": market,
        "assets": reports,
    }
    outdir = Path("reports/morning")
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "morning_summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for asset, report in reports.items():
        (outdir / f"{asset}_morning.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    messages = [
        build_market_message(market),
        build_line_message(reports["00631L"]),
        build_line_message(reports["00981A"]),
    ]
    (outdir / "line_messages.json").write_text(
        json.dumps(messages, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print("✅ 07:00盤前報告完成")
    return output


if __name__ == "__main__":
    run_morning()
