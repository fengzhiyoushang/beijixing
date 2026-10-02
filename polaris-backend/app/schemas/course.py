"""课程表模块出入参（学期 / 课程 / 节次 / 批量导入）。"""
from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HHMM = r"^\d{2}:\d{2}$"


class SemesterIn(BaseModel):
    name: str = Field(max_length=64)
    start_date: date | None = None
    end_date: date | None = None
    total_weeks: int = Field(default=20, ge=1, le=30)
    is_current: bool = False


class SemesterUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    total_weeks: int | None = Field(default=None, ge=1, le=30)
    is_current: bool | None = None


class ScheduleIn(BaseModel):
    weekday: int = Field(ge=1, le=7, description="1=周一 … 7=周日")
    start_section: int = Field(default=1, ge=1, le=12)
    end_section: int = Field(default=2, ge=1, le=12)
    start_time: str = Field(default="08:00", pattern=HHMM)
    end_time: str = Field(default="09:40", pattern=HHMM)
    weeks: str = Field(default="1-16", max_length=64, description="1-16 / 1-16单 / 1,3,5-9")
    week_type: str = Field(default="全周", pattern="^(全周|单周|双周)$")
    location: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _check(self):
        if self.end_section < self.start_section:
            raise ValueError("结束节次不能小于起始节次")
        if self.start_time >= self.end_time:
            raise ValueError("结束时间必须晚于开始时间")
        return self


class CourseIn(BaseModel):
    name: str = Field(max_length=128)
    teacher: str | None = Field(default=None, max_length=64)
    location: str | None = Field(default=None, max_length=128)
    credit: float = Field(default=0.0, ge=0, le=20)
    course_type: str = Field(default="必修", max_length=32)
    color: str = Field(default="#4ade80", max_length=16)
    note: str | None = None
    semester_id: int | None = None
    schedules: list[ScheduleIn] = Field(default_factory=list, description="节次安排，可多段")


class CourseUpdate(BaseModel):
    name: str | None = None
    teacher: str | None = None
    location: str | None = None
    credit: float | None = Field(default=None, ge=0, le=20)
    course_type: str | None = None
    color: str | None = None
    note: str | None = None
    semester_id: int | None = None
    schedules: list[ScheduleIn] | None = Field(default=None, description="传入则整体替换")


class CourseImportIn(BaseModel):
    """批量导入（Excel/JSON 统一入口）。"""

    semester_id: int | None = None
    replace: bool = Field(default=False, description="是否清空当前学期课程后再导入")
    courses: list[CourseIn] = Field(min_length=1)


class ConflictItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    weekday: int
    start_time: str
    end_time: str
    weeks: str
    course_a: str
    course_b: str
    location_a: str | None = None
    location_b: str | None = None
    reason: str = "时间重叠且周次相交"


class TimetableSlot(BaseModel):
    course_id: int
    name: str
    teacher: str | None = None
    location: str | None = None
    color: str | None = None
    weekday: int
    start_time: str
    end_time: str
    start_section: int | None = None
    end_section: int | None = None
    weeks: str | None = None
    status: str | None = Field(default=None, description="done|current|upcoming")
