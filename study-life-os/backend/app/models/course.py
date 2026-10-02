from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(128))
    teacher: Mapped[str | None] = mapped_column(String(64), nullable=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    color: Mapped[str | None] = mapped_column(String(16), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    slots: Mapped[list["ClassSlot"]] = relationship(
        "ClassSlot", back_populates="course", cascade="all, delete-orphan",
        lazy="selectin", order_by="ClassSlot.weekday",
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "teacher": self.teacher,
            "location": self.location,
            "color": self.color,
            "remark": self.remark,
            "slots": [s.to_dict() for s in self.slots],
        }


class ClassSlot(Base):
    """一门课可有多个上课时段；它是冲突检测与今日课程的最小单位。"""

    __tablename__ = "class_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    weekday: Mapped[int] = mapped_column(Integer)              # 1=周一 … 7=周日
    start_time: Mapped[str] = mapped_column(String(5))          # "08:00"
    end_time: Mapped[str] = mapped_column(String(5))            # "09:40"
    start_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_week: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weeks_text: Mapped[str | None] = mapped_column(String(32), nullable=True)  # "1-16周"

    course: Mapped["Course"] = relationship(back_populates="slots")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "weekday": self.weekday,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "start_week": self.start_week,
            "end_week": self.end_week,
            "weeks_text": self.weeks_text,
        }
