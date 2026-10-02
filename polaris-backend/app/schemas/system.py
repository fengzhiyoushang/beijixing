"""系统管理出入参。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ConfigIn(BaseModel):
    key: str = Field(max_length=64)
    value: dict = Field(default_factory=dict)
    group: str = Field(default="general", max_length=32)
    description: str | None = None
    is_public: bool = True


class ConfigUpdate(BaseModel):
    value: dict | None = None
    group: str | None = None
    description: str | None = None
    is_public: bool | None = None


class BackupIn(BaseModel):
    scope: str = Field(default="user", pattern="^(user|full)$",
                       description="user: 仅当前用户数据；full: 全库")
    note: str | None = None
    tables: list[str] | None = Field(default=None, description="指定表，缺省为全部")
