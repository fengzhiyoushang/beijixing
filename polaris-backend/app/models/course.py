"""② 课程表：学期 + 课程 + 节次/周次安排。"""
from __future__ import annotations

from datetime import date

from sqlalchemy import Boolean, Date, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, day, iso
from app.utils.timeutil import current_week, section_to_time


class Semester(Base, TimestampMixin):
    """学期管理。"""

    __tablename__ = "semesters"
    __table_args__ = (
        Index("ix_semesters_user_current", "user_id", "is_current"),
        {"comment": "学期表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64), comment="如 2026-2027 学年第一学期")
    start_date: Mapped[date | None] = mapped_column(Date, default=None)
    end_date: Mapped[date | None] = mapped_column(Date, default=None)
    total_weeks: Mapped[int] = mapped_column(Integer, default=20)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)

    courses: Mapped[list["Course"]] = relationship(back_populates="semester",
                                                   cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "start_date": day(self.start_date),
            "end_date": day(self.end_date),
            "total_weeks": self.total_weeks,
            "is_current": self.is_current,
            "current_week": current_week(self.start_date) if self.start_date else None,
            "created_at": iso(self.created_at),
        }


class Course(Base, TimestampMixin):
    """课程（学期、课程名、老师、教室、学分、备注）。"""

    __tablename__ = "courses"
    __table_args__ = (
        Index("ix_courses_user_semester", "user_id", "semester_id"),
        Index("ix_courses_name", "name"),
        {"comment": "课程表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    semester_id: Mapped[int | None] = mapped_column(
        ForeignKey("semesters.id", ondelete="SET NULL"), default=None, comment="所属学期")

    name: Mapped[str] = mapped_column(String(128), comment="课程名")
    teacher: Mapped[str | None] = mapped_column(String(64), default=None)
    location: Mapped[str | None] = mapped_column(String(128), default=None, comment="默认教室")
    credit: Mapped[float] = mapped_column(Float, default=0.0, comment="学分")
    course_type: Mapped[str] = mapped_column(String(32), default="必修", comment="必修/选修/实验")
    color: Mapped[str] = mapped_column(String(16), default="#4ade80", comment="课表配色")
    note: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(String(16), default="personal",
                                        comment="personal=个人课表 | classroom=教室课表（空教室页导入，仅用于占用预测）")

    semester: Mapped[Semester | None] = relationship(back_populates="courses")
    schedules: Mapped[list["CourseSchedule"]] = relationship(
        back_populates="course", cascade="all, delete-orphan", lazy="selectin")

    def to_dict(self, with_schedules: bool = True) -> dict:
        data = {
            "id": self.id,
            "semester_id": self.semester_id,
            "name": self.name,
            "teacher": self.teacher,
            "location": self.location,
            "credit": self.credit,
            "course_type": self.course_type,
            "color": self.color,
            "note": self.note,
            "source": self.source,
            "created_at": iso(self.created_at),
        }
        if with_schedules:
            data["schedules"] = [s.to_dict() for s in self.schedules]
        return data


class CourseSchedule(Base, TimestampMixin):
    """节次/周次安排（一门课可有多段）。"""

    __tablename__ = "course_schedules"
    __table_args__ = (
        Index("ix_schedules_course_weekday", "course_id", "weekday"),
        Index("ix_schedules_weekday_section", "weekday", "start_section"),
        {"comment": "课程节次安排表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)

    weekday: Mapped[int] = mapped_column(Integer, comment="1=周一 … 7=周日")
    start_section: Mapped[int] = mapped_column(Integer, default=1, comment="起始节次")
    end_section: Mapped[int] = mapped_column(Integer, default=2, comment="结束节次")
    start_time: Mapped[str] = mapped_column(String(5), default="08:00", comment="HH:MM")
    end_time: Mapped[str] = mapped_column(String(5), default="09:40", comment="HH:MM")
    weeks: Mapped[str] = mapped_column(String(64), default="1-16", comment="周次表达式 1-16 / 1-16单")
    week_type: Mapped[str] = mapped_column(String(8), default="全周", comment="全周/单周/双周")
    location: Mapped[str | None] = mapped_column(String(128), default=None, comment="该节次教室")

    course: Mapped[Course] = relationship(back_populates="schedules")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "weekday": self.weekday,
            "weekday_cn": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][self.weekday - 1],
            "start_section": self.start_section,
            "end_section": self.end_section,
            "start_time": self.start_time or section_to_time(self.start_section),
            "end_time": self.end_time or section_to_time(self.end_section),
            "weeks": self.weeks,
            "week_type": self.week_type,
            "location": self.location,
        }
