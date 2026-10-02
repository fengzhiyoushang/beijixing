"""⑥ 学习记录表：日期、科目、时长、完成任务、模考成绩。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, day, iso


class StudyRecord(Base, TimestampMixin):
    __tablename__ = "study_records"
    __table_args__ = (
        Index("ix_study_user_date", "user_id", "date"),
        Index("ix_study_user_subject", "user_id", "subject"),
        {"comment": "学习记录表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    task_id: Mapped[int | None] = mapped_column(
        ForeignKey("ddl_tasks.id", ondelete="SET NULL"), default=None, comment="关联完成的任务")

    date: Mapped[date] = mapped_column(Date, default=date.today, comment="学习日期")
    subject: Mapped[str] = mapped_column(String(32), default="综合", comment="科目")
    minutes: Mapped[int] = mapped_column(Integer, default=0, comment="学习时长（分钟）")
    content: Mapped[str | None] = mapped_column(Text, default=None, comment="学习内容/完成任务描述")
    mood: Mapped[int | None] = mapped_column(Integer, default=None, comment="状态 1~5")
    focus_score: Mapped[int | None] = mapped_column(Integer, default=None, comment="专注度 1~100")

    # 模考成绩
    mock_name: Mapped[str | None] = mapped_column(String(64), default=None, comment="模考名称")
    mock_score: Mapped[float | None] = mapped_column(Float, default=None, comment="模考得分")
    mock_full_score: Mapped[float | None] = mapped_column(Float, default=None, comment="满分")

    started_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": day(self.date),
            "subject": self.subject,
            "minutes": self.minutes,
            "hours": round((self.minutes or 0) / 60, 2),
            "content": self.content,
            "mood": self.mood,
            "focus_score": self.focus_score,
            "task_id": self.task_id,
            "mock_name": self.mock_name,
            "mock_score": self.mock_score,
            "mock_full_score": self.mock_full_score,
            "mock_rate": round(self.mock_score / self.mock_full_score, 3)
            if self.mock_score and self.mock_full_score else None,
            "started_at": iso(self.started_at),
            "ended_at": iso(self.ended_at),
            "created_at": iso(self.created_at),
        }
