from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class KaoyanGoal(Base):
    """考研目标：detail 存各科目 {name:{target,current,max}}。"""

    __tablename__ = "kaoyan_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    target_school: Mapped[str] = mapped_column(String(128))
    target_major: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_target: Mapped[float] = mapped_column(Float, default=0)
    total_current: Mapped[float] = mapped_column(Float, default=0)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    phases: Mapped[list["PlanPhase"]] = relationship(
        "PlanPhase", back_populates="goal", cascade="all, delete-orphan",
        lazy="selectin", order_by="PlanPhase.sort_no",
    )

    def to_dict(self) -> dict:
        days_left = (self.exam_date - date.today()).days if self.exam_date else None
        return {
            "id": self.id,
            "target_school": self.target_school,
            "target_major": self.target_major,
            "target_year": self.target_year,
            "exam_date": self.exam_date.isoformat() if self.exam_date else None,
            "days_left": days_left,
            "total_target": self.total_target,
            "total_current": self.total_current,
            "detail": self.detail or {},
            "status": self.status,
            "phases": [p.to_dict() for p in self.phases],
        }


class PlanPhase(Base):
    """阶段规划：基础 / 强化 / 冲刺 …"""

    __tablename__ = "plan_phases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    goal_id: Mapped[int] = mapped_column(ForeignKey("kaoyan_goals.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    objective: Mapped[str | None] = mapped_column(Text, nullable=True)
    focus: Mapped[dict] = mapped_column(JSON, default=dict)   # 各科时间分配等
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|active|done
    sort_no: Mapped[int] = mapped_column(Integer, default=0)

    goal: Mapped[KaoyanGoal] = relationship(back_populates="phases")
    tasks: Mapped[list["PlanTask"]] = relationship(
        "PlanTask", back_populates="phase", cascade="all, delete-orphan", lazy="selectin"
    )

    def to_dict(self) -> dict:
        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t.done)
        return {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "objective": self.objective,
            "focus": self.focus or {},
            "status": self.status,
            "sort_no": self.sort_no,
            "task_total": total,
            "task_done": done,
        }


class PlanTask(Base):
    """每日任务拆解（可勾选、可写复盘）。"""

    __tablename__ = "plan_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("plan_phases.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str | None] = mapped_column(String(32), nullable=True)
    planned_minutes: Mapped[int] = mapped_column(Integer, default=60)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    done_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    phase: Mapped[PlanPhase] = relationship(back_populates="tasks")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phase_id": self.phase_id,
            "date": self.date.isoformat() if self.date else None,
            "title": self.title,
            "subject": self.subject,
            "planned_minutes": self.planned_minutes,
            "done": self.done,
            "done_minutes": self.done_minutes,
            "review_note": self.review_note,
        }
