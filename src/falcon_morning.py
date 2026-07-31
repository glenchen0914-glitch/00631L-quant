from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from src.assets import ASSETS
from src.falcon_engine import evaluate, save_report
from src.morning import collect_overnight, score_market


def _safe_float(value: Any) -> float | None:
    try:
        x = float(value)
        return x if pd.notna(x) else None
    except (TypeError, ValueError):
        return None


def _events() -> list[str]:
    return [x.strip() for x in os.getenv("FALCON_EVENTS", "").split(",") if x.strip()]


def _position(asset: str) -> int:
    p = Path("data/manual/positions.json")
    if not p.exists():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get(asset, 0))
    except Exception:
        return 0


def _vix(raw: dict[str, Any]) -> tuple[float | None, float | None]:
    item = raw.get("VIX", {})
    return _safe_float(item.get("close")), _safe_float(item.get("change_pct"))


def build_line_message(asset: str, report: dict[str, Any]) -> str:
    gate = report["gate"]
    score = report["scores"]
    risk = report["risk"]
    reasons = "；".join(gate["reasons"][:2])
    return "\n".join([
        f"{asset} Falcon 07:00盤前",
        f"市場環境：{report['overnight_market']['label']} {report['overnight_market']['score']}/100",
        f"Gate上限：{gate['cap_pct']}%（{gate['level']}）",
        f"策略分數：{score['total']}/100｜趨勢{score['trend']} 拉回{score['pullback']} 動能{score['momentum']}",
        f"目標倉位：{report['position']['target_pct']}%",
        f"執行：{report['action']}",
        "開盤規則：實際Gap需09:00後確認；開高逾2.5%至少等至09:15",
        f"參考停損：{risk['initial_stop']:.2f}｜首段停利：{risk['first_take_profit']:.2f}",
        f"Gate原因：{reasons}",
    ])


def run_falcon_morning() -> dict[str, Any]:
    raw = collect_overnight()
    market = score_market(raw)
    vix_level, vix_change = _vix(raw)
    output: dict[str, Any] = {}

    for asset, spec in ASSETS.items():
        fpath = Path(spec["features_path"])
        if not fpath.exists():
            raise FileNotFoundError(f"缺少收盤特徵檔：{fpath}，請先執行14:35流程")
        df = pd.read_parquet(fpath)
        report = evaluate(
            df,
            events=_events(),
            vix_level=vix_level,
            vix_change_pct=vix_change,
            gap_pct=None,
            current_position=_position(asset),
        )
        report.update({
            "asset_code": asset,
            "asset_name": spec["name"],
            "session": "premarket",
            "overnight_market": market,
            "overnight_raw": raw,
            "gap_status": "待09:00取得實際開盤價後判定",
        })
        path = Path(spec["reports_dir"]) / "falcon_morning.json"
        save_report(report, path)
        report["line_message"] = build_line_message(asset, report)
        output[asset] = report

    Path("reports/falcon_morning_summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


if __name__ == "__main__":
    reports = run_falcon_morning()
    for report in reports.values():
        print(report["line_message"])
        print("-" * 30)
