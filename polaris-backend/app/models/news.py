"""新闻资讯：抓取源配置 + 文章存储（增量去重）+ 抓取日志。

合规说明：仅抓取公开可访问的 RSS / 页面，控制频率、不绕过登录与防护、
不抓取个人信息与付费内容；增量抓取按 URL 指纹去重，避免重复请求。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import LongText, TimestampMixin, iso


class NewsSource(Base, TimestampMixin):
    __tablename__ = "news_sources"
    __table_args__ = (
        Index("ix_news_sources_category", "category"),
        {"comment": "新闻抓取源（RSS/网页）"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(80), comment="来源名称")
    url: Mapped[str] = mapped_column(String(500), comment="RSS 或页面地址")
    category: Mapped[str] = mapped_column(String(24), default="综合",
                                          comment="财经/科技/考研就业/综合")
    mode: Mapped[str] = mapped_column(String(16), default="rss", comment="rss | focused")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    interval_min: Mapped[int] = mapped_column(Integer, default=30, comment="最小抓取间隔（分钟）")
    last_crawled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "category": self.category,
            "mode": self.mode,
            "enabled": self.enabled,
            "interval_min": self.interval_min,
            "last_crawled_at": iso(self.last_crawled_at),
        }


class NewsItem(Base, TimestampMixin):
    __tablename__ = "news_items"
    __table_args__ = (
        Index("ix_news_items_url_hash", "url_hash", unique=True),
        Index("ix_news_items_category_pub", "category", "published_at"),
        {"comment": "新闻条目（url_hash 唯一实现增量去重）"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("news_sources.id", ondelete="SET NULL"), default=None)
    source_name: Mapped[str | None] = mapped_column(String(80), default=None)
    category: Mapped[str] = mapped_column(String(24), default="综合", index=True)
    title: Mapped[str] = mapped_column(String(300), comment="标题")
    summary: Mapped[str | None] = mapped_column(Text, default=None, comment="摘要")
    content: Mapped[str | None] = mapped_column(LongText, default=None, comment="正文（聚焦抓取）")
    url: Mapped[str] = mapped_column(String(700), comment="原文链接")
    url_hash: Mapped[str] = mapped_column(String(64), comment="URL 指纹，用于增量去重")
    image_url: Mapped[str | None] = mapped_column(String(700), default=None)
    author: Mapped[str | None] = mapped_column(String(120), default=None)
    tags: Mapped[str | None] = mapped_column(String(300), default=None, comment="逗号分隔标签")
    published_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, index=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, comment="收藏（供 AI/复习）")

    def to_dict(self, with_content: bool = False) -> dict:
        data = {
            "id": self.id,
            "source_id": self.source_id,
            "source_name": self.source_name or "",
            "category": self.category,
            "title": self.title,
            "summary": self.summary or "",
            "url": self.url,
            "image_url": self.image_url or "",
            "author": self.author or "",
            "tags": [t for t in (self.tags or "").split(",") if t],
            "published_at": iso(self.published_at),
            "is_read": self.is_read,
            "is_starred": self.is_starred,
            "created_at": iso(self.created_at),
        }
        if with_content:
            data["content"] = self.content or ""
        return data


class NewsCrawlLog(Base):
    __tablename__ = "news_crawl_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    stage: Mapped[str] = mapped_column(String(16), comment="general | focused | incremental")
    source_name: Mapped[str | None] = mapped_column(String(80), default=None)
    found: Mapped[int] = mapped_column(Integer, default=0, comment="发现条数")
    new_items: Mapped[int] = mapped_column(Integer, default=0, comment="增量新增条数")
    enriched: Mapped[int] = mapped_column(Integer, default=0, comment="聚焦抓取补全正文条数")
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    message: Mapped[str | None] = mapped_column(String(500), default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "stage": self.stage,
            "source_name": self.source_name or "",
            "found": self.found,
            "new_items": self.new_items,
            "enriched": self.enriched,
            "ok": self.ok,
            "message": self.message or "",
            "created_at": iso(self.created_at),
        }
