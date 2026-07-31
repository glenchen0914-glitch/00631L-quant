from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

REQUIRED_MODULES = ("pandas", "numpy", "yfinance", "pyarrow", "sklearn")


def check(label: str, ok: bool, detail: str = "") -> bool:
    icon = "✅" if ok else "❌"
    print(f"{icon} {label}" + (f"：{detail}" if detail else ""))
    return ok


def main() -> int:
    critical = True
    critical &= check("Python", sys.version_info >= (3, 11), sys.version.split()[0])
    for name in REQUIRED_MODULES:
        critical &= check(f"套件 {name}", importlib.util.find_spec(name) is not None)

    for directory in ("data", "data/manual", "reports", "reports/morning"):
        p = Path(directory)
        try:
            p.mkdir(parents=True, exist_ok=True)
            probe = p / ".falcon_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            check(f"目錄 {directory}", True, "可寫入")
        except Exception as exc:
            critical = False
            check(f"目錄 {directory}", False, str(exc))

    token = bool(os.getenv("LINE_CHANNEL_ACCESS_TOKEN", "").strip())
    user_id = bool(os.getenv("LINE_USER_ID", "").strip())
    required = os.getenv("LINE_PUSH_REQUIRED", "false").lower() == "true"
    line_ok = token and user_id
    if required:
        critical &= check("LINE Secrets", line_ok, "已設定" if line_ok else "缺 LINE_CHANNEL_ACCESS_TOKEN 或 LINE_USER_ID")
    else:
        check("LINE Secrets", line_ok, "已設定" if line_ok else "未設定；本次允許跳過推播")

    print("✅ Falcon Doctor 通過" if critical else "❌ Falcon Doctor 未通過")
    return 0 if critical else 1


if __name__ == "__main__":
    raise SystemExit(main())
