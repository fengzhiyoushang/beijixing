"""系统管理服务：配置管理、数据备份/恢复、库表统计。"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.config import settings
from app.core.database import engine, server_status
from app.core.exceptions import AppError, NotFoundError
from app.models import ALL_TABLES
from app.models.system import DataBackup, SystemConfig

logger = logging.getLogger("polaris.system")

# 用户维度备份涉及的表（按外键依赖顺序）
USER_TABLES = [
    "semesters", "courses", "course_schedules",
    "ddl_tasks", "subtasks",
    "classroom_status_logs",
    "study_records",
    "kaoyan_targets", "kaoyan_plan_phases", "kaoyan_plan_tasks",
    "knowledge_folders", "knowledge_docs", "knowledge_chunks",
    "finance_records", "finance_budgets",
    "health_records", "health_settings",
    "ai_sessions", "ai_messages",
]


# ─────────── 配置 ───────────
def list_configs(db: Session, *, public_only: bool = False, group: str | None = None) -> list[SystemConfig]:
    query = db.query(SystemConfig)
    if public_only:
        query = query.filter(SystemConfig.is_public.is_(True))
    if group:
        query = query.filter(SystemConfig.group == group)
    return query.order_by(SystemConfig.group, SystemConfig.key).all()


def get_config(db: Session, key: str) -> SystemConfig | None:
    return db.query(SystemConfig).filter(SystemConfig.key == key).first()


def set_config(db: Session, payload) -> SystemConfig:
    config = get_config(db, payload.key)
    if config:
        config.value = payload.value
        config.group = payload.group or config.group
        config.description = payload.description or config.description
        config.is_public = payload.is_public
    else:
        config = SystemConfig(key=payload.key, value=payload.value, group=payload.group,
                              description=payload.description, is_public=payload.is_public)
        db.add(config)
    db.commit()
    db.refresh(config)
    return config


def update_config(db: Session, key: str, payload) -> SystemConfig:
    config = get_config(db, key)
    if not config:
        raise NotFoundError("配置项不存在")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(config, field, value)
    db.commit()
    db.refresh(config)
    return config


def delete_config(db: Session, key: str) -> None:
    config = get_config(db, key)
    if not config:
        raise NotFoundError("配置项不存在")
    db.delete(config)
    db.commit()


def runtime_info() -> dict:
    """运行态信息（不含任何密钥）。"""
    from app.ai.deepseek import deepseek

    return {
        "app": {"name": settings.APP_NAME, "version": settings.APP_VERSION,
                "debug": settings.DEBUG, "api_prefix": settings.API_PREFIX},
        "database": server_status(),
        "cache": cache.health(),
        "ai": deepseek.status(),
        "embedding": {"provider": settings.EMBEDDING_PROVIDER, "dim": settings.EMBEDDING_DIM},
        "limits": {"max_upload_mb": settings.MAX_UPLOAD_MB, "max_tool_rounds": settings.MAX_TOOL_ROUNDS,
                   "rag_top_k": settings.RAG_TOP_K},
        "cors_origins": settings.cors_origin_list,
    }


# ─────────── 库表统计 ───────────
def table_stats(db: Session) -> list[dict]:
    """各表行数（用于系统管理页与备份前概览）。"""
    from sqlalchemy import text

    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    result = []
    for table in ALL_TABLES:
        if table not in existing:
            result.append({"table": table, "rows": 0, "exists": False})
            continue
        try:
            count = int(db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
        except Exception:                        # pragma: no cover
            count = -1
        result.append({"table": table, "rows": count, "exists": True})
    return result


# ─────────── 备份 ───────────
def _dump_table(db: Session, table: str, user_id: int | None) -> list[dict]:
    from sqlalchemy import MetaData, Table

    meta = MetaData()
    tbl = Table(table, meta, autoload_with=engine)
    stmt = select(tbl)
    columns = {c.name for c in tbl.columns}
    if user_id is not None and "user_id" in columns:
        stmt = stmt.where(tbl.c.user_id == user_id)
    rows = db.execute(stmt).mappings().all()
    out = []
    for row in rows:
        item = {}
        for key, value in dict(row).items():
            item[key] = value.isoformat() if isinstance(value, (datetime,)) else (
                value.isoformat() if hasattr(value, "isoformat") else value)
        out.append(item)
    return out


def create_backup(db: Session, user_id: int | None, payload) -> DataBackup:
    tables = payload.tables or (ALL_TABLES if payload.scope == "full" else USER_TABLES)
    scoped_user = None if payload.scope == "full" else user_id

    dump: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}
    for table in tables:
        try:
            rows = _dump_table(db, table, scoped_user)
        except Exception as exc:                 # pragma: no cover
            logger.warning("备份表 %s 失败：%s", table, exc)
            continue
        dump[table] = rows
        counts[table] = len(rows)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"backup-{payload.scope}-{stamp}.json"
    path: Path = settings.backup_path / filename
    payload_json = {
        "meta": {
            "created_at": datetime.now().isoformat(),
            "scope": payload.scope,
            "user_id": scoped_user,
            "app": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "tables": list(dump.keys()),
            "row_counts": counts,
        },
        "data": dump,
    }
    path.write_text(json.dumps(payload_json, ensure_ascii=False, indent=2), encoding="utf-8")

    record = DataBackup(
        user_id=user_id, filename=filename, file_path=str(path),
        size_bytes=path.stat().st_size, tables=list(dump.keys()),
        row_counts=counts, scope=payload.scope, note=payload.note,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_backups(db: Session, user_id: int, *, include_full: bool = False) -> list[DataBackup]:
    query = db.query(DataBackup)
    if not include_full:
        query = query.filter(DataBackup.user_id == user_id)
    return query.order_by(DataBackup.created_at.desc()).limit(50).all()


def get_backup(db: Session, user_id: int, backup_id: int) -> DataBackup:
    record = db.get(DataBackup, backup_id)
    if not record or (record.user_id not in (None, user_id)):
        raise NotFoundError("备份不存在")
    return record


def delete_backup(db: Session, user_id: int, backup_id: int) -> None:
    record = get_backup(db, user_id, backup_id)
    try:
        Path(record.file_path).unlink(missing_ok=True)
    except OSError:                              # pragma: no cover
        logger.warning("备份文件删除失败：%s", record.file_path)
    db.delete(record)
    db.commit()


# 无 user_id 的子表：按父表归属清理（顺序：子 → 父）
CHILD_DELETE_SQL = {
    "course_schedules": "DELETE FROM course_schedules WHERE course_id IN "
                        "(SELECT id FROM courses WHERE user_id = :uid)",
    "subtasks": "DELETE FROM subtasks WHERE task_id IN "
                "(SELECT id FROM ddl_tasks WHERE user_id = :uid)",
    "kaoyan_plan_phases": "DELETE FROM kaoyan_plan_phases WHERE target_id IN "
                          "(SELECT id FROM kaoyan_targets WHERE user_id = :uid)",
    "kaoyan_plan_tasks": "DELETE FROM kaoyan_plan_tasks WHERE phase_id IN "
                         "(SELECT id FROM kaoyan_plan_phases WHERE target_id IN "
                         "(SELECT id FROM kaoyan_targets WHERE user_id = :uid))",
    "knowledge_chunks": "DELETE FROM knowledge_chunks WHERE doc_id IN "
                        "(SELECT id FROM knowledge_docs WHERE user_id = :uid)",
    "ai_messages": "DELETE FROM ai_messages WHERE session_id IN "
                   "(SELECT id FROM ai_sessions WHERE user_id = :uid)",
}


def _clear_user_data(db: Session, user_id: int, tables: list[str]) -> dict:
    """清理该用户在这些表中的数据（先子后父，兼容 MySQL 外键约束）。"""
    from sqlalchemy import MetaData, Table, delete, text

    meta = MetaData()
    cleared: dict[str, int] = {}
    for table in reversed(tables):                # 逆序 = 先子后父
        try:
            if table in CHILD_DELETE_SQL:
                result = db.execute(text(CHILD_DELETE_SQL[table]), {"uid": user_id})
                cleared[table] = result.rowcount or 0
            else:
                tbl = Table(table, meta, autoload_with=engine)
                if "user_id" not in tbl.columns:
                    continue
                result = db.execute(delete(tbl).where(tbl.c.user_id == user_id))
                cleared[table] = result.rowcount or 0
        except Exception as exc:                 # pragma: no cover
            logger.warning("清理表 %s 失败：%s", table, exc)
    db.commit()
    return cleared


def _coerce_row(table, row: dict) -> dict:
    """把 JSON 里的 ISO 字符串还原成列类型（date/datetime/bool）。"""
    from sqlalchemy import Boolean, Date, DateTime

    out: dict = {}
    for key, value in row.items():
        column = table.c.get(key)
        if column is None:
            continue
        if value is None:
            out[key] = None
        elif isinstance(column.type, DateTime) and isinstance(value, str):
            out[key] = datetime.fromisoformat(value)
        elif isinstance(column.type, Date) and isinstance(value, str):
            out[key] = date.fromisoformat(value)
        elif isinstance(column.type, Boolean) and isinstance(value, (int, str)):
            out[key] = bool(int(value)) if str(value).isdigit() else bool(value)
        else:
            out[key] = value
    return out


def restore_backup(db: Session, user_id: int, backup_id: int, *, confirm: bool = False) -> dict:
    """恢复用户维度备份（危险操作，需 confirm=true）。"""
    if not confirm:
        raise AppError("恢复操作需显式确认：confirm=true")
    record = get_backup(db, user_id, backup_id)
    if record.scope != "user":
        raise AppError("仅支持恢复 user 维度的备份")

    path = Path(record.file_path)
    if not path.exists():
        raise NotFoundError("备份文件已丢失")
    payload = json.loads(path.read_text(encoding="utf-8"))

    from sqlalchemy import MetaData, Table

    data = {table: rows for table, rows in payload.get("data", {}).items()
            if table in USER_TABLES}
    # 阶段一：按依赖逆序清理旧数据（先子后父）
    cleared = _clear_user_data(db, user_id, list(data.keys()))

    # 阶段二：按依赖正序回填（先父后子）
    restored: dict[str, int] = {}
    failed: dict[str, str] = {}
    meta = MetaData()
    for table in USER_TABLES:
        if table not in data:
            continue
        rows = data[table]
        try:
            tbl = Table(table, meta, autoload_with=engine)
            for row in rows:
                db.execute(tbl.insert().values(**_coerce_row(tbl, row)))
            db.commit()
            restored[table] = len(rows)
        except Exception as exc:                 # pragma: no cover
            db.rollback()
            logger.warning("恢复表 %s 失败：%s", table, exc)
            failed[table] = str(exc)[:160]
    return {"restored": restored, "cleared": cleared, "tables": len(restored),
            "failed": failed, "backup": record.filename}
