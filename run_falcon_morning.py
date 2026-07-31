import os

from src.falcon_morning import run_falcon_morning
from src.notify import push_line_messages

if __name__ == "__main__":
    reports = run_falcon_morning()
    messages = [r["line_message"] for r in reports.values()]
    token = os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip()
    user_id = os.getenv("LINE_USER_ID", "").strip()
    required = os.getenv("LINE_PUSH_REQUIRED", "false").lower() == "true"
    if token and user_id:
        push_line_messages(messages, token, user_id)
        print(f"✅ Falcon 07:00 LINE推播完成，共{len(messages)}則")
    elif required:
        raise RuntimeError("LINE Secrets尚未設定")
    else:
        print("⚠️ LINE Secrets尚未設定，已產生報告但跳過推播")
