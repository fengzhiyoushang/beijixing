"""系统管理：数据备份记录 + 系统配置。"""
from __future__ import annotations

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, iso


class DataBackup(Base, TimestampMixin):
    __tablename__ = "data_backups"
    __table_args__ = (
        Index("ix_backup_user", "user_id", "created_at"),
        {"comment": "数据备份记录表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None)
    filename: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    tables: Mapped[list] = mapped_column(JSON, default=list, comment="包含的表")
    row_counts: Mapped[dict] = mapped_column(JSON, default=dict, comment="各表行数")
    scope: Mapped[str] = mapped_column(String(16), default="user", comment="user|full")
    note: Mapped[str | None] = mapped_column(Text, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "file_path": self.file_path,
            "size_bytes": self.size_bytes,
            "size_kb": round((self.size_bytes or 0) / 1024, 1),
            "tables": self.tables or [],
            "row_counts": self.row_counts or {},
            "scope": self.scope,
            "note": self.note,
            "created_at": iso(self.created_at),
        }


class SystemConfig(Base, TimestampMixin):
    """键值配置（DeepSeek 开关、天气城市、功能开关等）。"""

    __tablename__ = "system_configs"
    __table_args__ = (
        Index("ix_sysconfig_key", "key", unique=True),
        {"comment": "系统配置表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(64), comment="配置键")
    value: Mapped[dict] = mapped_column(JSON, default=dict, comment="配置值")
    group: Mapped[str] = mapped_column(String(32), default="general", comment="分组")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    is_public: Mapped[bool] = mapped_column(default=True, comment="是否可被普通用户读取")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "key": self.key,
            "value": self.value,
            "group": self.group,
            "description": self.description,
            "is_public": self.is_public,
            "updated_at": iso(self.updated_at),
        }
