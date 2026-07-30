from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime
import pandas as pd

DEFAULT_STATE = {
    "symbol": "00631L",
    "position_pct": 0,
    "shares": 0,
    "average_cost": None,
    "realized_pnl": 0.0,
    "last_action": "無",
    "last_action_date": None,
}

def load_state(path: str = "reports/position_state.json") -> dict:
    p = Path(path)
    if not p.exists():
        return DEFAULT_STATE.copy()
    state = DEFAULT_STATE.copy()
    state.update(json.loads(p.read_text(encoding="utf-8")))
    return state

def save_state(state: dict, path: str = "reports/position_state.json") -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

def apply_manual_trades(
    state_path: str = "reports/position_state.json",
    trades_path: str = "data/manual/trades.csv",
) -> dict:
    state = load_state(state_path)
    p = Path(trades_path)
    if not p.exists():
        save_state(state, state_path)
        return state

    trades = pd.read_csv(p)
    if trades.empty:
        save_state(state, state_path)
        return state

    trades["date"] = trades["date"].astype(str)
    trades = trades.sort_values("date")
    last_applied = state.get("last_trade_id")

    for idx, row in trades.iterrows():
        trade_id = str(row.get("trade_id", idx))
        if last_applied is not None and trade_id <= str(last_applied):
            continue

        side = str(row["side"]).strip().upper()
        shares = int(row["shares"])
        price = float(row["price"])

        if side == "BUY":
            old_shares = int(state["shares"])
            old_cost = float(state["average_cost"] or 0)
            new_shares = old_shares + shares
            state["average_cost"] = (
                (old_shares * old_cost + shares * price) / new_shares
                if new_shares > 0 else None
            )
            state["shares"] = new_shares
            state["last_action"] = f"買進 {shares} 股"
        elif side == "SELL":
            sell_shares = min(shares, int(state["shares"]))
            avg = float(state["average_cost"] or 0)
            state["realized_pnl"] = float(state["realized_pnl"]) + sell_shares * (price - avg)
            state["shares"] = int(state["shares"]) - sell_shares
            if state["shares"] == 0:
                state["average_cost"] = None
            state["last_action"] = f"賣出 {sell_shares} 股"
        else:
            raise ValueError(f"不支援的 side：{side}")

        state["last_action_date"] = str(row["date"])
        state["last_trade_id"] = trade_id

    save_state(state, state_path)
    return state

def enrich_state_with_decision(state: dict, decision: dict) -> dict:
    state = dict(state)
    state["position_pct"] = decision.get("suggested_position_pct", state.get("position_pct", 0))
    close = decision.get("reference_close")
    avg = state.get("average_cost")
    if close is not None and avg:
        state["unrealized_return_pct"] = close / avg - 1
        state["unrealized_pnl"] = int(state.get("shares", 0)) * (close - avg)
    else:
        state["unrealized_return_pct"] = None
        state["unrealized_pnl"] = None
    return state
