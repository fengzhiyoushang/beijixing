"""DDL 任务模块出入参。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

PRIORITIES = {"high", "medium", "low"}
STATUSES = {"pending", "done", "archived"}


class SubTaskIn(BaseModel):
    title: str = Field(max_length=200)
    is_done: bool = False
    sort_order: int = 0
    note: str | None = None


class SubTaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    is_done: bool | None = None
    sort_order: int | None = None
    note: str | None = None


class TaskIn(BaseModel):
    title: str = Field(max_length=200)
    description: str | None = None
    category: str = Field(default="学习", max_length=32)
    priority: str = "medium"
    due_at: datetime | None = None
    remind_at: datetime | None = None
    tags: list[str] = Field(default_factory=list)
    estimate_minutes: int = Field(default=0, ge=0, le=24 * 60)
    course_id: int | None = None
    source: str = Field(default="web", max_length=16)
    subtasks: list[SubTaskIn] = Field(default_factory=list)

    @field_validator("priority")
    @classmethod
    def _priority(cls, v: str) -> str:
        if v not in PRIORITIES:
            raise ValueError("优先级必须是 high / medium / low")
        return v


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    category: str | None = None
    priority: str | None = None
    due_at: datetime | None = None
    remind_at: datetime | None = None
    status: str | None = None
    tags: list[str] | None = None
    estimate_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    course_id: int | None = None

    @field_validator("priority")
    @classmethod
    def _priority(cls, v):
        if v is not None and v not in PRIORITIES:
            raise ValueError("优先级必须是 high / medium / low")
        return v

    @field_validator("status")
    @classmethod
    def _status(cls, v):
        if v is not None and v not in STATUSES:
            raise ValueError("状态必须是 pending / done / archived")
        return v
