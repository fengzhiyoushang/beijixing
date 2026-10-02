"""数据层：SQLAlchemy 引擎 / 会话 / Base。

设计要点：
1. 默认 MySQL（pymysql），连接失败自动回退 SQLite，保证「克隆即跑」；
2. `get_db` 为 FastAPI 依赖，请求级会话并自动关闭；
3. 提供 `server_status()` 供 /system/health 展示真实后端类型。
"""
from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger("polaris.db")

_ACTIVE_BACKEND = "sqlite"


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""


def _build_engine() -> tuple[Engine, str]:
    """按配置创建引擎；MySQL 不可用时回退 SQLite。"""
    if settings.DB_BACKEND.lower() == "sqlite":
        engine = create_engine(
            settings.sqlite_url,
            echo=settings.DB_ECHO,
            future=True,
            connect_args={"check_same_thread": False},
        )
        return engine, "sqlite"

    try:
        engine = create_engine(
            settings.sqlalchemy_url,
            echo=settings.DB_ECHO,
            future=True,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
        )
        with engine.connect() as conn:          # 真实探活
            conn.execute(text("SELECT 1"))
        return engine, "mysql"
    except Exception as exc:                     # pragma: no cover - 环境相关
        logger.warning("MySQL 连接失败（%s），已回退 SQLite：%s", settings.MYSQL_HOST, exc)
        engine = create_engine(
            settings.sqlite_url,
            echo=settings.DB_ECHO,
            future=True,
            connect_args={"check_same_thread": False},
        )
        return engine, "sqlite"


engine, _ACTIVE_BACKEND = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级数据库会话。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """脚本 / 后台任务用的上下文会话（自动提交与回滚）。"""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """建表（幂等）。模型需先被导入以完成注册。"""
    from app import models  # noqa: F401  触发模型注册

    Base.metadata.create_all(bind=engine)


def drop_all() -> None:
    from app import models  # noqa: F401

    Base.metadata.drop_all(bind=engine)


def server_status() -> dict:
    """数据层健康状态。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        ok = True
    except SQLAlchemyError as exc:               # pragma: no cover
        logger.error("数据库探活失败：%s", exc)
        ok = False
    return {
        "engine": engine.name,
        "backend": _ACTIVE_BACKEND,
        "configured": settings.DB_BACKEND,
        "ok": ok,
        "url": engine.url.render_as_string(hide_password=True),
    }
