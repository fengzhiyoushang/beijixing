from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ClassroomRecord(Base):
    """空教室采集快照（小程序拍照标注写入）。"""

    __tablename__ = "classroom_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    building: Mapped[str] = mapped_column(String(64), index=True)
    room: Mapped[str] = mapped_column(String(32), index=True)
    occupied: Mapped[int] = mapped_column(Integer, default=0)   # 0 空闲 / 1 占用
    photo_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    weekday: Mapped[int] = mapped_column(Integer, index=True)   # 快照时 1~7
    hour: Mapped[int] = mapped_column(Integer, index=True)      # 快照时 0~23
    visited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "building": self.building,
            "room": self.room,
            "occupied": self.occupied,
            "photo_url": self.photo_url,
            "note": self.note,
            "weekday": self.weekday,
            "hour": self.hour,
            "visited_at": self.visited_at.isoformat() if self.visited_at else None,
        }
