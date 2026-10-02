"""⑨ 财务记录表 + 预算表。"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, day, iso


class FinanceRecord(Base, TimestampMixin):
    __tablename__ = "finance_records"
    __table_args__ = (
        Index("ix_fin_user_time", "user_id", "occurred_at"),
        Index("ix_fin_user_category", "user_id", "category"),
        Index("ix_fin_user_study", "user_id", "is_study"),
        {"comment": "财务记录表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    type: Mapped[str] = mapped_column(String(8), default="expense", comment="income|expense")
    category: Mapped[str] = mapped_column(String(32), default="餐饮")
    amount: Mapped[float] = mapped_column(Float, default=0.0, comment="金额（正数）")
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, comment="发生时间")
    note: Mapped[str | None] = mapped_column(Text, default=None)
    is_study: Mapped[bool] = mapped_column(Boolean, default=False, comment="是否学习支出")
    payment_method: Mapped[str] = mapped_column(String(24), default="微信", comment="微信/支付宝/现金/银行卡")
    related_task_id: Mapped[int | None] = mapped_column(
        ForeignKey("ddl_tasks.id", ondelete="SET NULL"), default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "type_label": "收入" if self.type == "income" else "支出",
            "category": self.category,
            "amount": round(self.amount or 0, 2),
            "signed_amount": round(self.amount if self.type == "income" else -self.amount, 2),
            "occurred_at": iso(self.occurred_at),
            "date": day(self.occurred_at.date()) if self.occurred_at else None,
            "note": self.note,
            "is_study": self.is_study,
            "payment_method": self.payment_method,
            "created_at": iso(self.created_at),
        }


class FinanceBudget(Base, TimestampMixin):
    __tablename__ = "finance_budgets"
    __table_args__ = (
        UniqueConstraint("user_id", "month", "category", name="uq_budget_user_month_cat"),
        Index("ix_fb_user_month", "user_id", "month"),
        {"comment": "预算表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    month: Mapped[str] = mapped_column(String(7), comment="YYYY-MM")
    category: Mapped[str] = mapped_column(String(32), default="*", comment="* 表示总预算")
    limit_amount: Mapped[float] = mapped_column(Float, default=0.0)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    def to_dict(self, used: float = 0.0) -> dict:
        limit = self.limit_amount or 0
        return {
            "id": self.id,
            "month": self.month,
            "category": self.category,
            "category_label": "总预算" if self.category == "*" else self.category,
            "limit_amount": round(limit, 2),
            "used": round(used, 2),
            "remaining": round(limit - used, 2),
            "usage_rate": round(used / limit, 4) if limit else 0,
        }
