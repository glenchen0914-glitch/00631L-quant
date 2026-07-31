from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from src.assets import ASSETS
from src.falcon_data import ensure_features
from src.research_engine import analyze_similar_history, save_research_report


def _paths(asset: str) -> tuple[Path, Path]:
    base = Path("reports/research")
    return base / f"{asset}_research.json", base / f"{asset}_research.csv"


def run_research(*, force_refresh: bool = True) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for asset in ASSETS:
        df = ensure_features(asset, force_refresh=force_refresh)
        report = analyze_similar_history(df, asset_code=asset)
        json_path, csv_path = _paths(asset)
        save_research_report(report, json_path, csv_path)
        output[asset] = report
        h5 = report["horizons"]["5"]
        print(
            f"✅ {asset} Research：樣本{h5['sample_count']}｜"
            f"5日勝率{h5['win_rate_pct']}%｜OOS方向正確率{report['validation_5d']['directional_accuracy_pct']}%"
        )
    Path("reports/research/research_summary.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


if __name__ == "__main__":
    run_research(force_refresh=True)
