"""健康模块出入参。"""
from __future__ import annotations

from datetime import date as DateType

from pydantic import BaseModel, Field

HHMM = r"^\d{2}:\d{2}$"


class HealthRecordIn(BaseModel):
    date: DateType | None = None
    sleep_minutes: int = Field(default=0, ge=0, le=24 * 60)
    exercise_minutes: int = Field(default=0, ge=0, le=24 * 60)
    sedentary_minutes: int = Field(default=0, ge=0, le=24 * 60)
    weight: float | None = Field(default=None, ge=20, le=300)
    water_ml: int = Field(default=0, ge=0, le=10000)
    steps: int = Field(default=0, ge=0, le=200000)
    mood: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None
    bed_time: str | None = Field(default=None, pattern=HHMM)
    wake_time: str | None = Field(default=None, pattern=HHMM)


class HealthRecordUpdate(BaseModel):
    sleep_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    exercise_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    sedentary_minutes: int | None = Field(default=None, ge=0, le=24 * 60)
    weight: float | None = Field(default=None, ge=20, le=300)
    water_ml: int | None = Field(default=None, ge=0, le=10000)
    steps: int | None = Field(default=None, ge=0, le=200000)
    mood: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None
    bed_time: str | None = Field(default=None, pattern=HHMM)
    wake_time: str | None = Field(default=None, pattern=HHMM)


class HealthSettingIn(BaseModel):
    sedentary_enabled: bool | None = None
    sedentary_interval_min: int | None = Field(default=None, ge=10, le=240)
    quiet_start: str | None = Field(default=None, pattern=HHMM)
    quiet_end: str | None = Field(default=None, pattern=HHMM)
    active_start: str | None = Field(default=None, pattern=HHMM)
    active_end: str | None = Field(default=None, pattern=HHMM)
    target_sleep_minutes: int | None = Field(default=None, ge=60, le=720)
    target_water_ml: int | None = Field(default=None, ge=200, le=6000)
    target_exercise_minutes: int | None = Field(default=None, ge=0, le=3000)


class HeartbeatIn(BaseModel):
    """前端心跳：用于久坐计时。"""

    spent_minutes: int = Field(default=0, ge=0, le=600, description="本次上报期间已投入的分钟数")
    note: str | None = None
