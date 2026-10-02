"""⑩ 健康记录表 + 健康设置表。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, day, iso


class HealthRecord(Base, TimestampMixin):
    """日期、睡眠时长、运动时长、久坐时长、体重、备注。"""

    __tablename__ = "health_records"
    __table_args__ = (
        UniqueConstraint("user_id", "date", name="uq_health_user_date"),
        Index("ix_health_user_date", "user_id", "date"),
        {"comment": "健康记录表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    date: Mapped[date] = mapped_column(Date, default=date.today)
    sleep_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="睡眠时长（分钟）")
    exercise_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="运动时长（分钟）")
    sedentary_minutes: Mapped[int] = mapped_column(Integer, default=0, comment="久坐时长（分钟）")
    weight: Mapped[float | None] = mapped_column(Float, default=None, comment="体重 kg")
    water_ml: Mapped[int] = mapped_column(Integer, default=0, comment="饮水量 ml")
    steps: Mapped[int] = mapped_column(Integer, default=0, comment="步数")
    mood: Mapped[int | None] = mapped_column(Integer, default=None, comment="心情 1~5")
    note: Mapped[str | None] = mapped_column(Text, default=None)

    bed_time: Mapped[str | None] = mapped_column(String(5), default=None, comment="入睡 HH:MM")
    wake_time: Mapped[str | None] = mapped_column(String(5), default=None, comment="起床 HH:MM")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "date": day(self.date),
            "sleep_minutes": self.sleep_minutes,
            "sleep_hours": round((self.sleep_minutes or 0) / 60, 2),
            "exercise_minutes": self.exercise_minutes,
            "sedentary_minutes": self.sedentary_minutes,
            "weight": self.weight,
            "water_ml": self.water_ml,
            "steps": self.steps,
            "mood": self.mood,
            "note": self.note,
            "bed_time": self.bed_time,
            "wake_time": self.wake_time,
            "created_at": iso(self.created_at),
        }


class HealthSetting(Base, TimestampMixin):
    """健康提醒设置（久坐间隔、免打扰时段、目标值）。"""

    __tablename__ = "health_settings"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_health_setting_user"),
        {"comment": "健康设置表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    sedentary_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sedentary_interval_min: Mapped[int] = mapped_column(Integer, default=45, comment="久坐提醒间隔")
    quiet_start: Mapped[str] = mapped_column(String(5), default="12:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="14:00")
    active_start: Mapped[str] = mapped_column(String(5), default="08:00")
    active_end: Mapped[str] = mapped_column(String(5), default="22:30")
    target_sleep_minutes: Mapped[int] = mapped_column(Integer, default=450)
    target_water_ml: Mapped[int] = mapped_column(Integer, default=2000)
    target_exercise_minutes: Mapped[int] = mapped_column(Integer, default=300, comment="周目标")

    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, default=None,
                                                              comment="最近心跳（久坐计时基准）")

    def to_dict(self) -> dict:
        return {
            "sedentary_enabled": self.sedentary_enabled,
            "sedentary_interval_min": self.sedentary_interval_min,
            "quiet_start": self.quiet_start,
            "quiet_end": self.quiet_end,
            "active_start": self.active_start,
            "active_end": self.active_end,
            "target_sleep_minutes": self.target_sleep_minutes,
            "target_water_ml": self.target_water_ml,
            "target_exercise_minutes": self.target_exercise_minutes,
            "last_heartbeat_at": iso(self.last_heartbeat_at),
        }
