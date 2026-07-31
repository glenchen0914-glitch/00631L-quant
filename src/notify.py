from __future__ import annotations
import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from src.report_designer import build_falcon_message

LINE_API = "https://api.line.me/v2/bot/message/push"

def _load_decision(path: str = "reports/daily_decision.json") -> dict:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"找不到決策檔：{path}")
    return json.loads(p.read_text(encoding="utf-8"))

def build_line_message(decision: dict) -> str:
    grade = decision.get("confidence_grade", {})
    regime = decision.get("market_regime", {})
    plan = decision.get("entry_plan", {})
    reasons = decision.get("decision_explanation", {})
    pos = reasons.get("positive", [])
    neg = reasons.get("negative", [])
    missing = reasons.get("missing", [])

    lines = [
        f"{decision.get('asset_code', '00631L')} 每日決策",
        f"資料日期：{decision.get('data_date', '-')}",
        "",
        f"結論：{decision.get('action', '-')}",
        f"建議持股：{decision.get('suggested_position_pct', 0)}%",
        f"信心：{grade.get('grade', '-')}級 {grade.get('score', 0)}/100",
        f"{decision.get('progress_label', '落底進度')}：{decision.get('bottom_progress_pct', 0)}%",
        f"市場環境：{regime.get('label', '-')} {regime.get('score', 0)}/100",
        f"參考收盤：{decision.get('reference_close', 0):.2f}",
        "",
        "分批價位：",
        f"第一筆 {plan.get('first', 0):.2f}",
        f"第二筆 {plan.get('second', 0):.2f}",
        f"第三筆 {plan.get('third', 0):.2f}",
        f"防守線 {plan.get('stop', 0):.2f}",
    ]

    if pos:
        lines += ["", "支持理由："] + [f"• {x}" for x in pos[:3]]
    if neg:
        lines += ["", "反對理由："] + [f"• {x}" for x in neg[:4]]
    if missing:
        lines += ["", "缺少資料："] + [f"• {x}" for x in missing[:3]]

    lines += ["", "完整儀表板請查看 GitHub Actions 執行產物或 Repository reports/dashboard.html"]
    return "\n".join(lines)


def push_line_messages(texts: list[str], token: str, user_id: str) -> None:
    messages = [{"type": "text", "text": text[:5000]} for text in texts[:5]]
    body = json.dumps({"to": user_id, "messages": messages}).encode("utf-8")
    req = urllib.request.Request(
        LINE_API,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status >= 300:
                raise RuntimeError(f"LINE API 回傳狀態 {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LINE 推播失敗：HTTP {exc.code} {detail}") from exc

def main() -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()
    required = os.getenv("LINE_PUSH_REQUIRED", "false").lower() == "true"

    if not token or not user_id:
        msg = "LINE Secrets 尚未設定，跳過推播。"
        if required:
            raise RuntimeError(msg)
        print("⚠️", msg)
        return

    falcon_paths = [
        Path("reports/falcon_decision.json"),
        Path("reports/00981A/falcon_decision.json"),
    ]
    if all(path.exists() for path in falcon_paths):
        reports = [json.loads(path.read_text(encoding="utf-8")) for path in falcon_paths]
        texts = [build_falcon_message(r, session="close") for r in reports]
    else:
        # 相容舊版：Falcon報告尚未生成時才使用舊決策檔。
        legacy_paths = [
            Path("reports/daily_decision.json"),
            Path("reports/00981A/daily_decision.json"),
        ]
        decisions = []
        for path in legacy_paths:
            if not path.exists():
                raise FileNotFoundError(f"找不到決策檔：{path}")
            decisions.append(json.loads(path.read_text(encoding="utf-8")))
        texts = [build_line_message(d) for d in decisions]

    push_line_messages(texts, token, user_id)
    print(f"✅ LINE 雙標的推播完成，共 {len(texts)} 則")

if __name__ == "__main__":
    main()
