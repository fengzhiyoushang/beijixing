from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class HealthLog(Base):
    """健康记录：sleep/wake/sedentary/water/exercise/other"""

    __tablename__ = "health_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    kind: Mapped[str] = mapped_column(String(16), index=True, default="other")
    happened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)   # 睡眠/运动时长
    value: Mapped[float | None] = mapped_column(Float, nullable=True)     # 饮水量 ml 等
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date: Mapped[date] = mapped_column(Date, index=True, default=date.today)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "happened_at": self.happened_at.isoformat() if self.happened_at else None,
            "minutes": self.minutes,
            "value": self.value,
            "note": self.note,
            "date": self.date.isoformat() if self.date else None,
        }


class HealthSetting(Base):
    """久坐/作息个性化配置（双端共用，Web 可编辑）。"""

    __tablename__ = "health_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    sedentary_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    sedentary_interval_min: Mapped[int] = mapped_column(Integer, default=45)
    quiet_start: Mapped[str] = mapped_column(String(5), default="23:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="07:00")
    active_start: Mapped[str] = mapped_column(String(5), default="07:00")
    active_end: Mapped[str] = mapped_column(String(5), default="23:00")
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self) -> dict:
        return {
            "sedentary_enabled": bool(self.sedentary_enabled),
            "sedentary_interval_min": self.sedentary_interval_min,
            "quiet_start": self.quiet_start,
            "quiet_end": self.quiet_end,
            "active_start": self.active_start,
            "active_end": self.active_end,
            "last_heartbeat_at": self.last_heartbeat_at.isoformat() if self.last_heartbeat_at else None,
        }
