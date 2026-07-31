from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pandas as pd

from src.assets import ASSETS, run_dual
from src.falcon_engine import evaluate, save_report


def _load_position(asset: str) -> int:
    p = Path("data/manual/positions.json")
    if not p.exists():
        return 0
    try:
        return int(json.loads(p.read_text(encoding="utf-8")).get(asset, 0))
    except Exception:
        return 0


def _events() -> list[str]:
    raw = os.getenv("FALCON_EVENTS", "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def run_falcon_close() -> dict[str, Any]:
    legacy = run_dual()
    output: dict[str, Any] = {}
    for asset, spec in ASSETS.items():
        df = pd.read_parquet(spec["features_path"])
        report = evaluate(
            df,
            events=_events(),
            vix_level=float(os.getenv("FALCON_VIX_LEVEL", "nan")),
            vix_change_pct=float(os.getenv("FALCON_VIX_CHANGE_PCT", "nan")),
            gap_pct=float(os.getenv(f"FALCON_{asset}_GAP_PCT", "nan")),
            current_position=_load_position(asset),
        )
        report["asset_code"] = asset
        report["asset_name"] = spec["name"]
        report["reference_close"] = float(df["close"].iloc[-1])
        report["legacy_reference"] = {
            "action": legacy[asset].get("action"),
            "position_pct": legacy[asset].get("suggested_position_pct"),
        }
        out = Path(spec["reports_dir"]) / "falcon_decision.json"
        save_report(report, out)
        output[asset] = report
    Path("reports/falcon_summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


if __name__ == "__main__":
    result = run_falcon_close()
    for asset, report in result.items():
        print(f"{asset}: {report['action']}｜Gate {report['gate']['cap_pct']}%｜Score {report['scores']['total']}")
