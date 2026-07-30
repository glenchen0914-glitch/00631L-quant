from src.pipeline import run
from src.performance import update_performance
from src.publish_summary import main as publish_summary
from src.notify import main as notify_line
from src.position import apply_manual_trades, enrich_state_with_decision, save_state
from src.research import update_research_log
from src.scanner import scan_universe
import json
from pathlib import Path

def main() -> None:
    run()
    update_performance()
    update_research_log()

    state = apply_manual_trades()
    decision = json.loads(Path("reports/daily_decision.json").read_text(encoding="utf-8"))
    state = enrich_state_with_decision(state, decision)
    save_state(state)

    try:
        scan_universe()
    except Exception as exc:
        print(f"⚠️ 多商品掃描失敗但不影響主流程：{exc}")

    publish_summary()
    notify_line()

if __name__ == "__main__":
    main()
