"""③ DDL 任务表 + 子任务。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, iso

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class DdlTask(Base, TimestampMixin):
    __tablename__ = "ddl_tasks"
    __table_args__ = (
        Index("ix_tasks_user_status_due", "user_id", "status", "due_at"),
        Index("ix_tasks_user_category", "user_id", "category"),
        Index("ix_tasks_user_priority", "user_id", "priority"),
        {"comment": "DDL 任务表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[int | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL"), default=None, comment="关联课程")

    title: Mapped[str] = mapped_column(String(200), comment="标题")
    description: Mapped[str | None] = mapped_column(Text, default=None)
    category: Mapped[str] = mapped_column(String(32), default="学习", comment="分类：学习/课程/生活/考研")
    priority: Mapped[str] = mapped_column(String(8), default="medium", comment="high|medium|low")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="截止时间")
    status: Mapped[str] = mapped_column(String(16), default="pending", comment="pending|done|archived")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    tags: Mapped[list] = mapped_column(JSON, default=list, comment="标签数组")
    remind_at: Mapped[datetime | None] = mapped_column(DateTime, default=None, comment="提醒时间")
    estimate_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="预计耗时(分钟)")
    source: Mapped[str] = mapped_column(String(16), default="web", comment="web|miniapp|ai")

    subtasks: Mapped[list["SubTask"]] = relationship(
        back_populates="task", cascade="all, delete-orphan", lazy="selectin",
        order_by="SubTask.sort_order")

    # ── 派生字段 ──
    def remaining_seconds(self, now: datetime | None = None) -> int | None:
        if not self.due_at:
            return None
        return int((self.due_at - (now or datetime.now())).total_seconds())

    @property
    def overdue(self) -> bool:
        return bool(self.due_at and self.status == "pending" and self.due_at < datetime.now())

    def to_dict(self) -> dict:
        remain = self.remaining_seconds()
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "priority_label": {"high": "高", "medium": "中", "low": "低"}.get(self.priority, "中"),
            "due_at": iso(self.due_at),
            "status": self.status,
            "completed_at": iso(self.completed_at),
            "tags": self.tags or [],
            "remind_at": iso(self.remind_at),
            "estimate_minutes": self.estimate_minutes,
            "course_id": self.course_id,
            "source": self.source,
            "remaining_seconds": remain,
            "overdue": self.overdue,
            "subtasks": [s.to_dict() for s in self.subtasks],
            "subtask_done": sum(1 for s in self.subtasks if s.is_done),
            "subtask_total": len(self.subtasks),
            "created_at": iso(self.created_at),
        }


class SubTask(Base, TimestampMixin):
    __tablename__ = "subtasks"
    __table_args__ = (
        Index("ix_subtasks_task", "task_id", "sort_order"),
        {"comment": "子任务表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("ddl_tasks.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    is_done: Mapped[bool] = mapped_column(default=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    task: Mapped[DdlTask] = relationship(back_populates="subtasks")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "title": self.title,
            "is_done": self.is_done,
            "sort_order": self.sort_order,
            "note": self.note,
        }
