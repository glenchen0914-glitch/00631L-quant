from __future__ import annotations
import json
import os
from pathlib import Path

from src.notify import push_line_messages


def main() -> None:
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()
    required = os.getenv("LINE_PUSH_REQUIRED", "false").lower() == "true"

    if not token or not user_id:
        msg = "LINE Secrets尚未設定，跳過07:00盤前推播。"
        if required:
            raise RuntimeError(msg)
        print("⚠️", msg)
        return

    path = Path("reports/morning/line_messages.json")
    if not path.exists():
        raise FileNotFoundError(path)
    texts = json.loads(path.read_text(encoding="utf-8"))
    push_line_messages(texts, token, user_id)
    print(f"✅ 07:00盤前LINE推播完成，共{len(texts)}則")


if __name__ == "__main__":
    main()
