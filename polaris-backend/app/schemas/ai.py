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
