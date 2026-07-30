from __future__ import annotations
from pathlib import Path
import json
import pandas as pd

def update_research_log(
    leaderboard_path: str = "reports/strategy_leaderboard.csv",
    output_path: str = "reports/strategy_research_log.csv",
) -> None:
    p = Path(leaderboard_path)
    if not p.exists():
        raise FileNotFoundError(p)
    board = pd.read_csv(p).head(20).copy()
    board["research_date"] = pd.Timestamp.now().strftime("%Y-%m-%d")
    keep = [
        c for c in [
            "research_date","name","description","final_score","score",
            "trades_test","profit_factor_test","max_drawdown_test",
            "wf_windows","wf_positive_windows","wf_median_pf","wf_median_return"
        ] if c in board.columns
    ]
    board = board[keep]
    out = Path(output_path)
    if out.exists():
        old = pd.read_csv(out)
        old = old[old["research_date"].astype(str) != board["research_date"].iloc[0]]
        board = pd.concat([old, board], ignore_index=True)
    out.parent.mkdir(parents=True, exist_ok=True)
    board.to_csv(out, index=False)
    print(f"✅ 策略研究紀錄已更新：{out}")

if __name__ == "__main__":
    update_research_log()
