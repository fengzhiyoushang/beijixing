from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Task(Base):
    """DDL 任务：全生命周期 status: pending | done | canceled"""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(16), default="study")   # study|work|life
    priority: Mapped[str] = mapped_column(String(8), default="medium")   # high|medium|low
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)            # 0~100
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self, now: datetime | None = None) -> dict:
        now = now or datetime.now()
        remaining = None
        overdue = False
        if self.due_at and self.status == "pending":
            delta = (self.due_at - now).total_seconds()
            remaining = max(int(delta), 0)
            overdue = delta < 0
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "priority": self.priority,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "status": self.status,
            "progress": self.progress,
            "done_at": self.done_at.isoformat() if self.done_at else None,
            "tags": self.tags or [],
            "remaining_seconds": remaining,
            "overdue": overdue,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
