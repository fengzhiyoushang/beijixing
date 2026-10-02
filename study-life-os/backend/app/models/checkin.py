from datetime import date, datetime

from sqlalchemy import Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CheckinRecord(Base):
    """学习打卡：subject 科目/主题，minutes 专注分钟数。"""

    __tablename__ = "checkin_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    subject: Mapped[str] = mapped_column(String(64))
    minutes: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1~5
    date: Mapped[date] = mapped_column(Date, index=True, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "subject": self.subject,
            "minutes": self.minutes,
            "content": self.content,
            "mood": self.mood,
            "date": self.date.isoformat() if self.date else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
