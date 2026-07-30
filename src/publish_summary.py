from __future__ import annotations
import json
from pathlib import Path

def main() -> None:
    p = Path("reports/daily_decision.json")
    if not p.exists():
        raise FileNotFoundError(p)
    d = json.loads(p.read_text(encoding="utf-8"))
    g = d.get("confidence_grade", {})
    r = d.get("market_regime", {})
    lines = [
        "# 00631L 每日決策",
        "",
        f"- 資料日期：{d.get('data_date')}",
        f"- 結論：**{d.get('action')}**",
        f"- 建議持股：**{d.get('suggested_position_pct')}%**",
        f"- 信心：**{g.get('grade')}級（{g.get('score')}/100）**",
        f"- 落底進度：**{d.get('bottom_progress_pct')}%**",
        f"- 市場環境：**{r.get('label')}（{r.get('score')}/100）**",
        "",
        "完整內容請開啟 `reports/dashboard.html`。",
    ]
    Path("reports/README.md").write_text("\n".join(lines), encoding="utf-8")
    print("✅ reports/README.md 已更新")

if __name__ == "__main__":
    main()
