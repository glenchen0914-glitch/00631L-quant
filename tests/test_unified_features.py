from pathlib import Path
import sys, json, tempfile, types
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if "yfinance" not in sys.modules:
    yf = types.ModuleType("yfinance")
    yf.download = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("offline"))
    sys.modules["yfinance"] = yf

from src.position import load_state, save_state, apply_manual_trades, enrich_state_with_decision
from src.research import update_research_log

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    state_path = td/"state.json"
    trades = td/"trades.csv"
    trades.write_text(
        "trade_id,date,side,shares,price,note\n"
        "1,2026-07-30,BUY,1000,28.0,first\n"
        "2,2026-07-31,BUY,500,27.0,second\n"
        "3,2026-08-01,SELL,300,29.0,trim\n",
        encoding="utf-8"
    )
    state = apply_manual_trades(str(state_path), str(trades))
    assert state["shares"] == 1200
    assert state["average_cost"] is not None
    assert state["realized_pnl"] > 0

    decision = {"reference_close": 30.0, "suggested_position_pct": 40}
    enriched = enrich_state_with_decision(state, decision)
    assert enriched["position_pct"] == 40
    assert enriched["unrealized_pnl"] is not None

    lb = td/"leaderboard.csv"
    lb.write_text(
        "name,description,final_score,trades_test,profit_factor_test,max_drawdown_test,wf_windows,wf_positive_windows,wf_median_pf,wf_median_return\n"
        "S1,test,5.2,10,1.8,-0.15,4,3,1.5,0.08\n",
        encoding="utf-8"
    )
    out = td/"research.csv"
    update_research_log(str(lb), str(out))
    assert out.exists()

print("PASS: 部位狀態與策略研究")
