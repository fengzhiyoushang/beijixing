"""数据库初始化脚本。

用法：
    python scripts/init_db.py              # 建库 + 建表（幂等）
    python scripts/init_db.py --seed       # 建表 + 写入演示数据（账号 admin/admin123）
    python scripts/init_db.py --drop       # 先删表再重建（危险）
    python scripts/init_db.py --stats      # 查看各表行数

MySQL 模式会自动执行 CREATE DATABASE IF NOT EXISTS；连接失败则回退 SQLite。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Windows 控制台默认 GBK，强制 UTF-8 输出避免 ✓ 等符号报错
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):             # pragma: no cover
    pass

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.config import settings          # noqa: E402
from app.core.database import drop_all, init_db, server_status, session_scope  # noqa: E402


def ensure_mysql_database() -> None:
    if settings.DB_BACKEND.lower() != "mysql":
        print("· 当前为 SQLite 模式，跳过建库步骤")
        return
    try:
        engine = create_engine(settings.mysql_server_url, future=True)
        with engine.connect() as conn:
            conn.execute(text(
                f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DB}` "
                f"DEFAULT CHARACTER SET {settings.MYSQL_CHARSET} COLLATE {settings.MYSQL_CHARSET}_general_ci"
            ))
            conn.commit()
        engine.dispose()
        print(f"✓ MySQL 数据库已就绪：{settings.MYSQL_DB}")
    except Exception as exc:
        print(f"! MySQL 建库失败（{exc}），后续将使用 SQLite 回退")


def print_stats() -> None:
    from app.services import system_service

    with session_scope() as db:
        rows = system_service.table_stats(db)
    print(f"{'表名':<28}{'行数':>8}")
    print("-" * 38)
    for item in rows:
        flag = "" if item.get("exists", True) else "  (未创建)"
        print(f"{item['table']:<28}{item['rows']:>8}{flag}")
    print("-" * 38)
    print(f"合计：{sum(r['rows'] for r in rows if r['rows'] > 0)} 行")


def main() -> int:
    parser = argparse.ArgumentParser(description="北极星后端数据库初始化")
    parser.add_argument("--seed", action="store_true", help="写入演示数据")
    parser.add_argument("--drop", action="store_true", help="先删除所有表再重建")
    parser.add_argument("--stats", action="store_true", help="仅打印各表行数")
    args = parser.parse_args()

    if args.stats:
        print_stats()
        return 0

    print(f"→ 目标数据库：{settings.DB_BACKEND} / {settings.sqlalchemy_url.split('@')[-1]}")
    ensure_mysql_database()

    if args.drop:
        print("! 正在删除所有表…")
        drop_all()
    init_db()
    status = server_status()
    print(f"✓ 建表完成：engine={status['engine']} backend={status['backend']}")
    print_stats()

    if args.seed:
        from scripts.seed_demo import seed

        print("→ 写入演示数据…")
        seed(reset=args.drop)
        print_stats()

    print("\n启动服务： uvicorn app.main:app --reload --port 8000")
    print("接口文档： http://127.0.0.1:8000/docs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
