"""数据库核心：Engine / SessionLocal / Base / get_db / 建表与演示数据初始化。"""
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings

_url = settings.sqlalchemy_url
_kwargs: dict = {}
if _url.startswith("sqlite"):
    os.makedirs("data", exist_ok=True)
    _kwargs = {"connect_args": {"check_same_thread": False}}
else:
    _kwargs = {"pool_pre_ping": True, "pool_recycle": 3600}

engine = create_engine(_url, **_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """建表（开发模式；生产用 Alembic）并按需写入演示数据。"""
    from app import models  # noqa: F401  确保所有模型已注册
    Base.metadata.create_all(bind=engine)
    if settings.SEED_DEMO:
        from app.services.seed import seed_if_empty
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
