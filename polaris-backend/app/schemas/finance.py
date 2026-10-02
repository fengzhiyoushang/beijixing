"""财务模块出入参。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class FinanceRecordIn(BaseModel):
    type: str = Field(default="expense", description="income | expense")
    category: str = Field(default="餐饮", max_length=32)
    amount: float = Field(gt=0, le=1_000_000)
    occurred_at: datetime | None = None
    note: str | None = None
    is_study: bool = False
    payment_method: str = Field(default="微信", max_length=24)
    related_task_id: int | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v: str) -> str:
        if v not in {"income", "expense"}:
            raise ValueError("类型必须是 income 或 expense")
        return v


class FinanceRecordUpdate(BaseModel):
    type: str | None = None
    category: str | None = None
    amount: float | None = Field(default=None, gt=0, le=1_000_000)
    occurred_at: datetime | None = None
    note: str | None = None
    is_study: bool | None = None
    payment_method: str | None = None

    @field_validator("type")
    @classmethod
    def _type(cls, v):
        if v is not None and v not in {"income", "expense"}:
            raise ValueError("类型必须是 income 或 expense")
        return v


class BudgetIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$", description="YYYY-MM")
    category: str = Field(default="*", max_length=32, description="* 表示总预算")
    limit_amount: float = Field(gt=0, le=10_000_000)
    note: str | None = None


class BudgetUpdate(BaseModel):
    limit_amount: float | None = Field(default=None, gt=0, le=10_000_000)
    note: str | None = None
