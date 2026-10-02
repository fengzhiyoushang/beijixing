"""⑦ 考研目标表 + 阶段计划 + 计划任务。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, day, iso


class KaoyanTarget(Base, TimestampMixin):
    """目标院校、专业、各科分数线、当前成绩、差距分析。"""

    __tablename__ = "kaoyan_targets"
    __table_args__ = (
        Index("ix_kaoyan_user_status", "user_id", "status"),
        {"comment": "考研目标表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    school: Mapped[str] = mapped_column(String(128), comment="目标院校")
    major: Mapped[str] = mapped_column(String(128), comment="目标专业")
    degree_type: Mapped[str] = mapped_column(String(16), default="学硕", comment="学硕|专硕")
    exam_date: Mapped[date | None] = mapped_column(Date, default=None, comment="初试日期")
    status: Mapped[str] = mapped_column(String(16), default="active", comment="active|done|archived")

    # 各科分数线 / 当前成绩：[{subject, target, current, max, line, note}]
    subject_scores: Mapped[list] = mapped_column(JSON, default=list, comment="科目分数配置")
    total_target: Mapped[float] = mapped_column(Float, default=0.0, comment="总分目标")
    total_current: Mapped[float] = mapped_column(Float, default=0.0, comment="当前预估总分")

    gap_analysis: Mapped[dict] = mapped_column(JSON, default=dict, comment="差距分析结果快照")
    note: Mapped[str | None] = mapped_column(Text, default=None)

    phases: Mapped[list["KaoyanPlanPhase"]] = relationship(
        back_populates="target", cascade="all, delete-orphan", lazy="selectin",
        order_by="KaoyanPlanPhase.sort_order")

    @property
    def days_left(self) -> int | None:
        if not self.exam_date:
            return None
        return (self.exam_date - date.today()).days

    def to_dict(self, with_phases: bool = True) -> dict:
        data = {
            "id": self.id,
            "school": self.school,
            "major": self.major,
            "degree_type": self.degree_type,
            "exam_date": day(self.exam_date),
            "days_left": self.days_left,
            "status": self.status,
            "subject_scores": self.subject_scores or [],
            "total_target": self.total_target,
            "total_current": self.total_current,
            "total_gap": round((self.total_target or 0) - (self.total_current or 0), 1),
            "progress": round((self.total_current or 0) / self.total_target * 100, 1) if self.total_target else 0,
            "gap_analysis": self.gap_analysis or {},
            "note": self.note,
            "created_at": iso(self.created_at),
        }
        if with_phases:
            data["phases"] = [p.to_dict() for p in self.phases]
        return data


class KaoyanPlanPhase(Base, TimestampMixin):
    """阶段计划（基础/强化/冲刺）。"""

    __tablename__ = "kaoyan_plan_phases"
    __table_args__ = (
        Index("ix_kpp_target", "target_id", "sort_order"),
        {"comment": "考研阶段计划表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("kaoyan_targets.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(64), comment="阶段名")
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)
    focus: Mapped[str | None] = mapped_column(Text, default=None, comment="阶段重点")
    subjects: Mapped[list] = mapped_column(JSON, default=list, comment="涉及科目")
    progress: Mapped[int] = mapped_column(Integer, default=0, comment="完成度 0~100")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(16), default="manual", comment="manual|ai")

    target: Mapped[KaoyanTarget] = relationship(back_populates="phases")
    tasks: Mapped[list["KaoyanPlanTask"]] = relationship(
        back_populates="phase", cascade="all, delete-orphan", lazy="selectin",
        order_by="KaoyanPlanTask.plan_date")

    def to_dict(self, with_tasks: bool = True) -> dict:
        data = {
            "id": self.id,
            "target_id": self.target_id,
            "name": self.name,
            "start_date": day(self.start_date),
            "end_date": day(self.end_date),
            "focus": self.focus,
            "subjects": self.subjects or [],
            "progress": self.progress,
            "sort_order": self.sort_order,
            "source": self.source,
        }
        if with_tasks:
            data["tasks"] = [t.to_dict() for t in self.tasks]
        return data


class KaoyanPlanTask(Base, TimestampMixin):
    """每日/每周计划任务。"""

    __tablename__ = "kaoyan_plan_tasks"
    __table_args__ = (
        Index("ix_kpt_phase_date", "phase_id", "plan_date"),
        {"comment": "考研计划任务表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    phase_id: Mapped[int] = mapped_column(ForeignKey("kaoyan_plan_phases.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    subject: Mapped[str] = mapped_column(String(32), default="综合")
    minutes: Mapped[int] = mapped_column(Integer, default=60, comment="预计耗时")
    is_done: Mapped[bool] = mapped_column(default=False)
    plan_date: Mapped[date | None] = mapped_column(Date, default=None)

    phase: Mapped[KaoyanPlanPhase] = relationship(back_populates="tasks")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phase_id": self.phase_id,
            "title": self.title,
            "subject": self.subject,
            "minutes": self.minutes,
            "is_done": self.is_done,
            "plan_date": day(self.plan_date),
        }
