"""空教室模块出入参。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

HHMM = r"^\d{2}:\d{2}$"


class ClassroomIn(BaseModel):
    building: str = Field(max_length=64)
    room_no: str = Field(max_length=32)
    capacity: int = Field(default=0, ge=0, le=1000)
    seats: int = Field(default=0, ge=0, le=1000)
    open_time: str = Field(default="07:00", pattern=HHMM)
    close_time: str = Field(default="22:30", pattern=HHMM)
    floor: int | None = Field(default=None, ge=-3, le=30)
    room_type: str = Field(default="普通教室", max_length=24)
    has_projector: bool = True
    has_ac: bool = True
    note: str | None = None


class ClassroomUpdate(BaseModel):
    building: str | None = None
    room_no: str | None = None
    capacity: int | None = None
    seats: int | None = None
    open_time: str | None = Field(default=None, pattern=HHMM)
    close_time: str | None = Field(default=None, pattern=HHMM)
    floor: int | None = None
    room_type: str | None = None
    has_projector: bool | None = None
    has_ac: bool | None = None
    is_active: bool | None = None
    note: str | None = None


class StatusReportIn(BaseModel):
    """状态上报（Web 手动 / 小程序 / 课程推断）。"""

    building: str = Field(max_length=64)
    room_no: str = Field(max_length=32)
    status: str = Field(description="free | busy | unknown")
    occupied_seats: int = Field(default=0, ge=0)
    source: str = Field(default="manual", description="manual|miniapp|ai_vision|course_schedule")
    confidence: float = Field(default=1.0, ge=0, le=1)
    photo_url: str | None = None
    note: str | None = None
    recorded_at: datetime | None = Field(default=None, description="缺省为当前时间")

    @field_validator("status")
    @classmethod
    def _status(cls, v: str) -> str:
        if v not in {"free", "busy", "unknown"}:
            raise ValueError("状态必须是 free / busy / unknown")
        return v


class VisionRecognizeIn(BaseModel):
    """多模态识图：接收图片 base64，识别教室状态。"""

    building: str | None = Field(default=None, max_length=64)
    room_no: str | None = Field(default=None, max_length=32)
    image_base64: str = Field(description="base64（可含 data:image/jpeg;base64, 前缀）")
    save_log: bool = Field(default=True, description="是否落库为状态记录")
    note: str | None = None
