"""④ 教室信息表 + ⑤ 教室状态记录表 + 教室使用记录表（Excel 导入，防重复录入）。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String,
                        Text, UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, iso


class Classroom(Base, TimestampMixin):
    """教室静态信息（教学楼、编号、容量、开放时间）。"""

    __tablename__ = "classrooms"
    __table_args__ = (
        UniqueConstraint("building", "room_no", name="uq_classroom_building_room"),
        Index("ix_classrooms_building", "building"),
        {"comment": "教室信息表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    building: Mapped[str] = mapped_column(String(64), comment="教学楼")
    room_no: Mapped[str] = mapped_column(String(32), comment="教室编号")
    capacity: Mapped[int] = mapped_column(Integer, default=0, comment="容量")
    open_time: Mapped[str] = mapped_column(String(5), default="07:00", comment="开放时间 HH:MM")
    close_time: Mapped[str] = mapped_column(String(5), default="22:30", comment="关闭时间 HH:MM")
    floor: Mapped[int | None] = mapped_column(Integer, default=None)
    room_type: Mapped[str] = mapped_column(String(24), default="普通教室", comment="普通/机房/自习室/研讨间")
    has_projector: Mapped[bool] = mapped_column(Boolean, default=True)
    has_ac: Mapped[bool] = mapped_column(Boolean, default=True)
    seats: Mapped[int] = mapped_column(Integer, default=0, comment="座位数（可自习）")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "building": self.building,
            "room_no": self.room_no,
            "name": f"{self.building} {self.room_no}",
            "capacity": self.capacity,
            "seats": self.seats,
            "open_time": self.open_time,
            "close_time": self.close_time,
            "floor": self.floor,
            "room_type": self.room_type,
            "has_projector": self.has_projector,
            "has_ac": self.has_ac,
            "is_active": self.is_active,
            "note": self.note,
            "created_at": iso(self.created_at),
        }


class ClassroomStatusLog(Base, TimestampMixin):
    """教室状态记录（时间、状态、上报来源、识别置信度）。"""

    __tablename__ = "classroom_status_logs"
    __table_args__ = (
        Index("ix_csl_room_time", "building", "room_no", "recorded_at"),
        Index("ix_csl_weekday_hour", "weekday", "hour"),
        Index("ix_csl_user", "user_id", "recorded_at"),
        {"comment": "教室状态记录表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    classroom_id: Mapped[int | None] = mapped_column(
        ForeignKey("classrooms.id", ondelete="SET NULL"), default=None, index=True)
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), default=None, comment="上报人")

    building: Mapped[str] = mapped_column(String(64), comment="冗余教学楼，便于聚合")
    room_no: Mapped[str] = mapped_column(String(32), comment="冗余教室编号")
    status: Mapped[str] = mapped_column(String(16), default="free", comment="free|busy|unknown")
    occupied_seats: Mapped[int] = mapped_column(Integer, default=0, comment="已占用座位（估算）")
    source: Mapped[str] = mapped_column(String(24), default="manual",
                                        comment="manual|miniapp|ai_vision|course_schedule")
    confidence: Mapped[float] = mapped_column(Float, default=1.0, comment="识别置信度 0~1")
    photo_url: Mapped[str | None] = mapped_column(String(255), default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="记录时间")
    weekday: Mapped[int] = mapped_column(Integer, default=1, comment="1~7")
    hour: Mapped[int] = mapped_column(Integer, default=8, comment="0~23")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "classroom_id": self.classroom_id,
            "building": self.building,
            "room_no": self.room_no,
            "name": f"{self.building} {self.room_no}",
            "status": self.status,
            "status_label": {"free": "空闲", "busy": "占用", "unknown": "未知"}.get(self.status, "未知"),
            "occupied_seats": self.occupied_seats,
            "source": self.source,
            "confidence": round(self.confidence or 0, 3),
            "photo_url": self.photo_url,
            "note": self.note,
            "recorded_at": iso(self.recorded_at),
            "weekday": self.weekday,
            "hour": self.hour,
        }


class ClassroomUsageRecord(Base, TimestampMixin):
    """教室使用记录（Excel 导入）：同一教室同一日期时间段唯一，防止重复录入。"""

    __tablename__ = "classroom_usage_records"
    __table_args__ = (
        UniqueConstraint("building", "room_no", "use_date", "start_time", "end_time",
                         name="uq_usage_room_slot"),
        Index("ix_cur_room_date", "building", "room_no", "use_date"),
        {"comment": "教室使用记录表（防重复录入）"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    classroom_id: Mapped[int | None] = mapped_column(
        ForeignKey("classrooms.id", ondelete="SET NULL"), default=None, index=True)
    building: Mapped[str] = mapped_column(String(64), comment="教学楼")
    room_no: Mapped[str] = mapped_column(String(32), comment="教室编号")
    use_date: Mapped[date] = mapped_column(Date, comment="使用日期")
    start_time: Mapped[str] = mapped_column(String(5), comment="开始 HH:MM")
    end_time: Mapped[str] = mapped_column(String(5), comment="结束 HH:MM")
    status: Mapped[str] = mapped_column(String(16), default="busy", comment="free|busy")
    department: Mapped[str | None] = mapped_column(String(64), default=None, comment="使用部门")
    purpose: Mapped[str | None] = mapped_column(String(128), default=None, comment="用途")
    note: Mapped[str | None] = mapped_column(Text, default=None)
    source: Mapped[str] = mapped_column(String(24), default="excel", comment="excel|manual")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "building": self.building,
            "room_no": self.room_no,
            "name": f"{self.building} {self.room_no}",
            "use_date": self.use_date.isoformat() if self.use_date else None,
            "weekday": self.use_date.isoweekday() if self.use_date else None,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "status": self.status,
            "status_label": {"free": "空闲", "busy": "使用"}.get(self.status, self.status),
            "department": self.department,
            "purpose": self.purpose,
            "note": self.note,
            "source": self.source,
            "created_at": iso(self.created_at),
        }
