"""AI 模块出入参。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: int | None = Field(default=None, description="不传则新建会话")
    use_tools: bool = Field(default=True, description="是否启用 Function Call")
    use_rag: bool = Field(default=False, description="是否先做知识库检索增强")
    temperature: float = Field(default=0.7, ge=0, le=2)
    system: str | None = Field(default=None, description="自定义系统提示词")


class ToolCallIn(BaseModel):
    name: str = Field(description="工具名，见 GET /ai/tools")
    arguments: dict = Field(default_factory=dict)


class LlmCfgIn(BaseModel):
    base_url: str | None = Field(default=None, max_length=200)
    api_key: str | None = Field(default=None, max_length=200, description="留空/不传=保持原值")
    model: str | None = Field(default=None, max_length=80)
    vl_model: str | None = Field(default=None, max_length=80)
    timeout: int | None = Field(default=None, ge=5, le=600)
    quota: int | None = Field(default=None, ge=0, description="Token 预算，0=不限")


class LlmTestIn(BaseModel):
    base_url: str | None = None
    api_key: str | None = None
    model: str | None = None
    timeout: int | None = None
