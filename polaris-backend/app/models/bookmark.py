"""地址中心：用户自定义常用网址书签。"""
from __future__ import annotations

from sqlalchemy import ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, iso


class Bookmark(Base, TimestampMixin):
    __tablename__ = "bookmarks"
    __table_args__ = (
        Index("ix_bookmarks_user_category", "user_id", "category"),
        {"comment": "地址中心：常用网址书签"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(120), comment="站点名称")
    url: Mapped[str] = mapped_column(String(500), comment="完整链接")
    category: Mapped[str] = mapped_column(String(32), default="常用", comment="分组：学习/工具/生活/开发…")
    note: Mapped[str | None] = mapped_column(String(255), default=None, comment="备注")
    icon: Mapped[str | None] = mapped_column(String(8), default=None, comment="图标字符")
    color: Mapped[str | None] = mapped_column(String(16), default=None, comment="卡片主色")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    click_count: Mapped[int] = mapped_column(Integer, default=0, comment="打开次数")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "url": self.url,
            "category": self.category,
            "note": self.note or "",
            "icon": self.icon or "🔗",
            "color": self.color or "#4ade80",
            "sort_order": self.sort_order,
            "click_count": self.click_count,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }
