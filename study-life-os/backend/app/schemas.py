"""Pydantic v2 请求模式集中定义（响应统一走模型 to_dict，减少双份维护）。"""
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ORMMode(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ───────────────────────── auth ─────────────────────────
class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=6, max_length=128)
    nickname: Optional[str] = None


class LoginIn(BaseModel):
    username: str
    password: str


class WxLoginIn(BaseModel):
    code: str
    nickname: Optional[str] = None


# ───────────────────────── courses ─────────────────────────
class SlotIn(BaseModel):
    weekday: int = Field(ge=1, le=7)
    start_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(pattern=r"^\d{2}:\d{2}$")
    start_week: Optional[int] = None
    end_week: Optional[int] = None
    weeks_text: Optional[str] = None


class CourseIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    teacher: Optional[str] = None
    location: Optional[str] = None
    color: Optional[str] = None
    remark: Optional[str] = None
    slots: List[SlotIn] = Field(default_factory=list)


class CoursePatchIn(BaseModel):
    name: Optional[str] = None
    teacher: Optional[str] = None
    location: Optional[str] = None
    color: Optional[str] = None
    remark: Optional[str] = None
    slots: Optional[List[SlotIn]] = None


class CourseImportIn(BaseModel):
    courses: List[CourseIn] = Field(default_factory=list)


# ───────────────────────── tasks ─────────────────────────
class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    category: str = "study"
    priority: str = "medium"
    due_at: Optional[datetime] = None
    progress: int = Field(default=0, ge=0, le=100)
    tags: List[str] = Field(default_factory=list)


class TaskPatchIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    due_at: Optional[datetime] = None
    status: Optional[str] = None
    progress: Optional[int] = None
    tags: Optional[List[str]] = None


# ───────────────────────── checkin ─────────────────────────
class CheckinIn(BaseModel):
    subject: str = Field(min_length=1, max_length=64)
    minutes: int = Field(gt=0, le=24 * 60)
    content: Optional[str] = None
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    date: Optional[date] = None


# ───────────────────────── kaoyan ─────────────────────────
class GoalIn(BaseModel):
    target_school: str = Field(min_length=1, max_length=128)
    target_major: Optional[str] = None
    target_year: Optional[int] = None
    exam_date: Optional[date] = None
    total_target: float = 0
    total_current: float = 0
    detail: Dict[str, Any] = Field(default_factory=dict)
    status: str = "active"


class PhaseIn(BaseModel):
    name: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    objective: Optional[str] = None
    focus: Dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    sort_no: int = 0


class PlanTaskIn(BaseModel):
    date: date
    title: str
    subject: Optional[str] = None
    planned_minutes: int = 60


class PlanTaskPatchIn(BaseModel):
    title: Optional[str] = None
    subject: Optional[str] = None
    planned_minutes: Optional[int] = None
    done: Optional[bool] = None
    done_minutes: Optional[int] = None
    review_note: Optional[str] = None


class PlanGenerateIn(BaseModel):
    auto_daily: bool = True          # 是否同时生成近期每日任务
    daily_days: int = Field(default=3, ge=1, le=14)


class ReviewIn(BaseModel):
    days: int = Field(default=7, ge=1, le=30)


# ───────────────────────── knowledge ─────────────────────────
class DocIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = ""
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class DocPatchIn(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class QaIn(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)


# ───────────────────────── finance ─────────────────────────
class FinanceIn(BaseModel):
    type: str = Field(pattern="^(income|expense)$")
    category: str = "其他"
    amount: float = Field(gt=0)
    is_study: bool = False
    note: Optional[str] = None
    occurred_at: Optional[date] = None


class FinancePatchIn(BaseModel):
    type: Optional[str] = None
    category: Optional[str] = None
    amount: Optional[float] = None
    is_study: Optional[bool] = None
    note: Optional[str] = None
    occurred_at: Optional[date] = None


class BudgetIn(BaseModel):
    month: str = Field(pattern=r"^\d{4}-\d{2}$")
    category: str = "*"
    limit_amount: float = Field(ge=0)


# ───────────────────────── health ─────────────────────────
class HealthLogIn(BaseModel):
    kind: str = Field(pattern="^(sleep|wake|sedentary|water|exercise|other)$")
    minutes: Optional[int] = None
    value: Optional[float] = None
    note: Optional[str] = None
    happened_at: Optional[datetime] = None


class HealthSettingIn(BaseModel):
    sedentary_enabled: Optional[bool] = None
    sedentary_interval_min: Optional[int] = Field(default=None, ge=5, le=240)
    quiet_start: Optional[str] = None
    quiet_end: Optional[str] = None
    active_start: Optional[str] = None
    active_end: Optional[str] = None


# ───────────────────────── ai ─────────────────────────
class ChatIn(BaseModel):
    message: str = Field(min_length=1)
    session_id: Optional[int] = None
    source: str = "web"


class HeartbeatIn(BaseModel):
    client: str = "web"
