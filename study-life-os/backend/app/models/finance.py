from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class FinanceRecord(Base):
    """收支流水。is_study 标记学习投入（购书/课程/文具等）。"""

    __tablename__ = "finance_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    type: Mapped[str] = mapped_column(String(8), default="expense")  # income|expense
    category: Mapped[str] = mapped_column(String(32), default="其他")
    amount: Mapped[float] = mapped_column(Float, default=0)
    is_study: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    occurred_at: Mapped[date] = mapped_column(Date, index=True, default=date.today)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "category": self.category,
            "amount": round(self.amount, 2),
            "is_study": bool(self.is_study),
            "note": self.note,
            "occurred_at": self.occurred_at.isoformat() if self.occurred_at else None,
        }


class Budget(Base):
    """月度预算：category='*' 表示总预算。"""

    __tablename__ = "budgets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    month: Mapped[str] = mapped_column(String(7), index=True)  # "2025-08"
    category: Mapped[str] = mapped_column(String(32), default="*")
    limit_amount: Mapped[float] = mapped_column(Float, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "month": self.month,
            "category": self.category,
            "limit_amount": round(self.limit_amount, 2),
        }
