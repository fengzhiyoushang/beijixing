"""考研规划模块出入参。"""
from __future__ import annotations

from datetime import date
from datetime import date as DateType

from pydantic import BaseModel, Field, model_validator


class SubjectScoreIn(BaseModel):
    subject: str = Field(max_length=32)
    target: float = Field(default=0, ge=0, description="目标分")
    current: float = Field(default=0, ge=0, description="当前成绩")
    max: float = Field(default=100, gt=0, description="满分")
    line: float | None = Field(default=None, ge=0, description="国家线/院线")
    note: str | None = None


class KaoyanTargetIn(BaseModel):
    school: str = Field(max_length=128)
    major: str = Field(max_length=128)
    degree_type: str = Field(default="学硕", pattern="^(学硕|专硕)$")
    exam_date: date | None = None
    subject_scores: list[SubjectScoreIn] = Field(default_factory=list)
    total_target: float | None = Field(default=None, ge=0, description="不传则按各科目标求和")
    total_current: float | None = Field(default=None, ge=0, description="不传则按各科当前求和")
    note: str | None = None


class KaoyanTargetUpdate(BaseModel):
    school: str | None = None
    major: str | None = None
    degree_type: str | None = Field(default=None, pattern="^(学硕|专硕)$")
    exam_date: date | None = None
    subject_scores: list[SubjectScoreIn] | None = None
    total_target: float | None = None
    total_current: float | None = None
    status: str | None = Field(default=None, pattern="^(active|done|archived)$")
    note: str | None = None


class ScoreIn(BaseModel):
    """成绩录入：按科目更新当前成绩，可同时写入学习记录。"""

    subject: str = Field(max_length=32)
    current: float = Field(ge=0)
    mock_name: str | None = Field(default=None, max_length=64)
    add_study_record: bool = Field(default=False, description="是否同时写一条学习记录")
    minutes: int = Field(default=0, ge=0)
    date: DateType | None = None


class PlanGenerateIn(BaseModel):
    """计划生成参数（AI 或规则引擎）。"""

    total_weeks: int = Field(default=16, ge=4, le=40, description="剩余备考周数")
    daily_minutes: int = Field(default=300, ge=60, le=900, description="每日可投入分钟")
    use_ai: bool = Field(default=True, description="是否调用 DeepSeek 生成（失败自动回退规则引擎）")
    subjects: list[str] | None = Field(default=None, description="指定科目，缺省取目标各科")
    include_daily_tasks: bool = Field(default=True, description="是否同时生成每日任务拆解")
    replace_existing: bool = Field(default=False, description="是否清空旧阶段计划")


class PhaseIn(BaseModel):
    name: str = Field(max_length=64)
    start_date: date | None = None
    end_date: date | None = None
    focus: str | None = None
    subjects: list[str] = Field(default_factory=list)
    progress: int = Field(default=0, ge=0, le=100)
    sort_order: int = 0


class PhaseUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    focus: str | None = None
    subjects: list[str] | None = None
    progress: int | None = Field(default=None, ge=0, le=100)
    sort_order: int | None = None


class PlanTaskIn(BaseModel):
    phase_id: int
    title: str = Field(max_length=255)
    subject: str = Field(default="综合", max_length=32)
    minutes: int = Field(default=60, ge=0, le=600)
    plan_date: date | None = None


class PlanTaskUpdate(BaseModel):
    title: str | None = None
    subject: str | None = None
    minutes: int | None = Field(default=None, ge=0, le=600)
    is_done: bool | None = None
    plan_date: date | None = None
