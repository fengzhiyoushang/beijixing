"""知识库模块出入参（RAG 问答 / 检索）。"""
from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


class FolderIn(BaseModel):
    name: str = Field(max_length=64)
    parent_id: int | None = None
    icon: str = Field(default="≡", max_length=16)
    sort_order: int = 0


class FolderUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    icon: str | None = None
    sort_order: int | None = None


class DocIn(BaseModel):
    title: str = Field(max_length=255)
    content: str = Field(default="", description="Markdown / 纯文本正文")
    folder_id: int | None = None
    tags: list[str] = Field(default_factory=list)
    doc_type: str = Field(default="markdown", max_length=16)
    summary: str | None = None
    auto_vectorize: bool = Field(default=True, description="保存后自动切片向量化")


class DocUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    folder_id: int | None = None
    tags: list[str] | None = None
    summary: str | None = None
    re_vectorize: bool = Field(default=False, description="内容更新后是否重建向量")


class QaIn(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    doc_ids: list[int] | None = Field(default=None, description="限定文档范围")
    folder_id: int | None = None
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = Field(default="auto", pattern="^(auto|rag|extractive|chat)$",
                      description="auto: 有检索结果走 RAG，否则普通对话")
    history: list[dict] = Field(default_factory=list, description="历史消息 [{role, content}]")


class SearchIn(BaseModel):
    keyword: str = Field(min_length=1, max_length=200)
    folder_id: int | None = None
    mode: str = Field(default="hybrid", pattern="^(keyword|vector|hybrid)$")
    top_k: int = Field(default=8, ge=1, le=50)
