"""提醒扫描脚本：由 cron / 微信云托管定时触发器调用。

用法：
    python scripts/push_reminders.py                # 扫描并推送（DDL + 上课）
    python scripts/push_reminders.py --kind ddl      # 只扫 DDL
    python scripts/push_reminders.py --kind class    # 只扫上课提醒
    python scripts/push_reminders.py --ahead 60      # 覆盖提前分钟数

crontab 示例（每 10 分钟）：
    */10 * * * * cd /opt/polaris-backend && .venv/bin/python scripts/push_reminders.py >> backups/push.log 2>&1
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):             # pragma: no cover
    pass

from app.core.database import session_scope     # noqa: E402
from app.services import wechat_service          # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="北极星提醒扫描")
    parser.add_argument("--kind", choices=["all", "ddl", "class"], default="all")
    parser.add_argument("--ahead", type=int, default=None, help="提前分钟数（覆盖配置）")
    args = parser.parse_args()

    status = wechat_service.status()
    print(f"微信推送模式：{status['mode']}｜模板：{status['templates']}")
    if status["mode"] == "mock":
        print("! 未配置 WX_APPID/WX_APP_SECRET，本次只记录日志不会真实发送")

    async def run() -> dict:
        with session_scope() as db:
            if args.kind == "ddl":
                return {"ddl": await wechat_service.push_due_ddl(db, ahead_minutes=args.ahead)}
            if args.kind == "class":
                return {"class": await wechat_service.push_upcoming_class(db,
                                                                         ahead_minutes=args.ahead)}
            return await wechat_service.run_scan(db)

    result = asyncio.run(run())
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    sent = sum(part.get("sent", 0) for part in result.values() if isinstance(part, dict))
    print(f"✓ 扫描完成，实际发送 {sent} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
