"""学习记录模块出入参。"""
from __future__ import annotations

from datetime import date as DateType
from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class StudyRecordIn(BaseModel):
    date: DateType | None = None
    subject: str = Field(default="综合", max_length=32)
    minutes: int = Field(default=0, ge=0, le=24 * 60, description="学习时长（分钟）")
    content: str | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    focus_score: int | None = Field(default=None, ge=0, le=100)
    task_id: int | None = None
    mock_name: str | None = Field(default=None, max_length=64)
    mock_score: float | None = Field(default=None, ge=0)
    mock_full_score: float | None = Field(default=None, gt=0)
    started_at: datetime | None = None
    ended_at: datetime | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.mock_score is not None and self.mock_full_score is not None:
            if self.mock_score > self.mock_full_score:
                raise ValueError("模考得分不能超过满分")
        return self


class StudyRecordUpdate(BaseModel):
    date: DateType | None = None
    subject: str | None = None
    minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    content: str | None = None
    mood: int | None = Field(default=None, ge=1, le=5)
    focus_score: int | None = Field(default=None, ge=0, le=100)
    mock_name: str | None = None
    mock_score: float | None = Field(default=None, ge=0)
    mock_full_score: float | None = Field(default=None, gt=0)


class MockScoreIn(BaseModel):
    """模考成绩快速录入（可在 ai/工具中调用）。"""

    subject: str = Field(max_length=32)
    mock_name: str = Field(max_length=64)
    score: float = Field(ge=0)
    full_score: float = Field(gt=0)
    date: DateType | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _check(self):
        if self.score > self.full_score:
            raise ValueError("得分不能超过满分")
        return self
