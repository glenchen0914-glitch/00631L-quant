from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

def update_performance(
    decision_path: str = "reports/daily_decision.json",
    history_path: str = "reports/decision_history.csv",
) -> None:
    dpath = Path(decision_path)
    if not dpath.exists():
        raise FileNotFoundError(decision_path)

    d = json.loads(dpath.read_text(encoding="utf-8"))
    row = {
        "date": d.get("data_date"),
        "action": d.get("action"),
        "stage": d.get("stage"),
        "suggested_position_pct": d.get("suggested_position_pct"),
        "reference_close": d.get("reference_close"),
        "bottom_progress_pct": d.get("bottom_progress_pct"),
        "market_regime_score": d.get("market_regime", {}).get("score"),
        "confidence_grade": d.get("confidence_grade", {}).get("grade"),
        "confidence_score": d.get("confidence_grade", {}).get("score"),
        "strategy": d.get("strategy"),
        "model_probability": d.get("model_consensus", {}).get("probability"),
        "strategy_vote_ratio": d.get("ensemble_signal", {}).get("vote_ratio"),
    }

    hpath = Path(history_path)
    if hpath.exists():
        old = pd.read_csv(hpath)
        old = old[old["date"].astype(str) != str(row["date"])]
        out = pd.concat([old, pd.DataFrame([row])], ignore_index=True)
    else:
        out = pd.DataFrame([row])
    out = out.sort_values("date")
    hpath.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(hpath, index=False)
    print(f"✅ 決策歷史已更新：{hpath}")

if __name__ == "__main__":
    update_dual_performance()


def update_dual_performance() -> None:
    update_performance(
        "reports/daily_decision.json",
        "reports/decision_history.csv",
    )
    update_performance(
        "reports/00981A/daily_decision.json",
        "reports/00981A/decision_history.csv",
    )

