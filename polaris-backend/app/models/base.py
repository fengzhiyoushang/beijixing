"""模型公共基类与工具。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column

# 通用长文本：MySQL 用 LONGTEXT，其它方言回退 TEXT
LongText = Text().with_variant(LONGTEXT(), "mysql")


class TimestampMixin:
    """创建/更新时间戳（所有表统一具备）。"""

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, nullable=False,
                                                 comment="创建时间")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now,
                                                 nullable=False, comment="更新时间")


def iso(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def day(value) -> str | None:
    return value.strftime("%Y-%m-%d") if value else None
