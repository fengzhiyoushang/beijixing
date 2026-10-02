"""一次性数据迁移：MySQL(polaris_terminal) → SQLite（桌面版 userData 库）。

用法（在 polaris-backend 目录，用 venv 运行）：
    python scripts/migrate_mysql_to_sqlite.py --target "C:\\Users\\lenovo\\AppData\\Roaming\\polaris-desktop\\data\\polaris.db"
    # 可选覆盖源库参数：--host/--port/--user/--password/--db

要点：
- 目标库用同一套 ORM 模型建表（Base.metadata.create_all）；
- 按 sorted_tables 拓扑序逐表整行复制，显式携带主键 id；
- 复制完成后修正 sqlite_sequence，避免后续插入撞主键。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

from sqlalchemy import create_engine, insert, select, text  # noqa: E402

import app.models  # noqa: F401,E402  注册全部 ORM 模型
from app.core.database import Base  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="MySQL → SQLite 数据迁移")
    parser.add_argument("--target", required=True, help="目标 SQLite 文件路径")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--user", default="root")
    parser.add_argument("--password", default="trr4699288")
    parser.add_argument("--db", default="polaris_terminal")
    parser.add_argument("--fresh", action="store_true", help="目标文件已存在时先删除重建")
    args = parser.parse_args()

    target = Path(args.target)
    if target.exists() and args.fresh:
        target.unlink()
    target.parent.mkdir(parents=True, exist_ok=True)

    src_url = (f"mysql+pymysql://{args.user}:{args.password}"
               f"@{args.host}:{args.port}/{args.db}?charset=utf8mb4")
    dst_url = f"sqlite:///{target}"

    src = create_engine(src_url, future=True)
    with src.connect() as conn:
        conn.execute(text("SELECT 1"))
    print(f"✓ 源 MySQL 连接成功：{args.db}")

    dst = create_engine(dst_url, future=True, connect_args={"check_same_thread": False})
    Base.metadata.create_all(dst)
    print(f"✓ 目标 SQLite 建表完成：{target}")

    total = 0
    with dst.begin() as dconn:
        for table in Base.metadata.sorted_tables:
            name = table.name
            with src.connect() as sconn:
                rows = sconn.execute(select(table)).mappings().all()
            if not rows:
                print(f"  · {name:<26} 0 行")
                continue
            dconn.execute(insert(table), [dict(r) for r in rows])
            total += len(rows)
            print(f"  ✓ {name:<26} {len(rows)} 行")

    # 修正自增序列：仅当存在 AUTOINCREMENT（sqlite_sequence 表才会被创建）时处理
    with dst.begin() as dconn:
        has_seq = dconn.execute(text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
        )).scalar()
        if has_seq:
            seq_rows = dconn.execute(text("SELECT name FROM sqlite_sequence")).scalars().all()
            for name in seq_rows:
                pk = list(Base.metadata.tables[name].primary_key.columns)[0].name
                mx = dconn.execute(text(f"SELECT MAX({pk}) FROM `{name}`")).scalar()
                if mx is not None:
                    dconn.execute(
                        text("UPDATE sqlite_sequence SET seq = :v WHERE name = :n"),
                        {"v": mx, "n": name},
                    )
            print("✓ sqlite_sequence 已修正")
        else:
            print("· 无 AUTOINCREMENT 表，跳过 sqlite_sequence 修正")

    print(f"\n迁移完成：共 {total} 行 → {target}")
    src.dispose()
    dst.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
