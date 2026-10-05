"""考研情报缓存：目标院校/专业的历年初试·复试分数线与就业信息。

由聚焦爬虫定期抓取院校公开页面（研究生院 / 学院招生就业网），
以 school+major 为唯一键缓存，附数据来源与采集时间，供前端展示。
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import LongText, TimestampMixin, iso


class KaoyanIntel(Base, TimestampMixin):
    __tablename__ = "kaoyan_intel"
    __table_args__ = (
        Index("ix_kaoyan_intel_school_major", "school", "major", unique=True),
        {"comment": "考研情报缓存（分数线 + 就业，聚焦爬虫抓取）"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    school: Mapped[str] = mapped_column(String(128), comment="院校名")
    major: Mapped[str] = mapped_column(String(128), comment="专业名")
    major_code: Mapped[str | None] = mapped_column(String(32), default=None, comment="专业代码")

    # 结构化情报快照：{score_lines:[{year,...}], retest:{...}, employment:{...}, sources:[...]}
    payload: Mapped[dict] = mapped_column(LongText, default="{}", comment="JSON 字符串")
    source: Mapped[str | None] = mapped_column(String(300), default=None, comment="主要数据来源")
    crawled_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="采集时间")
    from_cache: Mapped[bool] = mapped_column(Boolean, default=True, comment="本次是否命中缓存")
    note: Mapped[str | None] = mapped_column(Text, default=None)

    def to_dict(self) -> dict:
        import json
        try:
            data = json.loads(self.payload or "{}")
        except Exception:
            data = {}
        return {
            "id": self.id,
            "school": self.school,
            "major": self.major,
            "major_code": self.major_code,
            "source": self.source or "",
            "crawled_at": iso(self.crawled_at),
            "from_cache": self.from_cache,
            **data,
        }
