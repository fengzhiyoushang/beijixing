"""微信订阅消息出入参。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class QuotaGrantIn(BaseModel):
    """小程序 wx.requestSubscribeMessage 成功后上报授权次数。"""

    kind: str = Field(default="ddl", pattern="^(ddl|class)$", description="ddl=任务提醒 class=上课提醒")
    times: int = Field(default=1, ge=1, le=50, description="本次获得的可推送次数")
    template_id: str | None = Field(default=None, max_length=64, description="缺省取服务端配置")


class PushTestIn(BaseModel):
    kind: str = Field(default="ddl", pattern="^(ddl|class)$")
    title: str = Field(default="测试提醒：操作系统实验报告", max_length=64)
    due_at: datetime | None = None
    category: str = Field(default="课程", max_length=16)
    location: str = Field(default="东一舍 A302", max_length=32)
