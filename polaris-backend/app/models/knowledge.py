"""⑧ 知识库：文件夹 + 文档（向量化状态）+ 切片向量。"""
from __future__ import annotations

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import LongText, TimestampMixin, iso


class KnowledgeFolder(Base, TimestampMixin):
    __tablename__ = "knowledge_folders"
    __table_args__ = (
        Index("ix_kf_user_parent", "user_id", "parent_id"),
        {"comment": "知识库文件夹表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_folders.id", ondelete="CASCADE"), default=None)
    icon: Mapped[str] = mapped_column(String(16), default="≡")
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "parent_id": self.parent_id,
            "icon": self.icon,
            "sort_order": self.sort_order,
            "created_at": iso(self.created_at),
        }


class KnowledgeDoc(Base, TimestampMixin):
    """文档标题、内容、标签、向量化状态、更新时间。"""

    __tablename__ = "knowledge_docs"
    __table_args__ = (
        Index("ix_kd_user_folder", "user_id", "folder_id"),
        Index("ix_kd_user_vector_status", "user_id", "vector_status"),
        Index("ix_kd_title", "title"),
        {"comment": "知识库文档表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    folder_id: Mapped[int | None] = mapped_column(
        ForeignKey("knowledge_folders.id", ondelete="SET NULL"), default=None, index=True)

    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(LongText, default="", comment="正文（Markdown / 纯文本）")
    summary: Mapped[str | None] = mapped_column(LongText, default=None, comment="摘要")
    tags: Mapped[list] = mapped_column(JSON, default=list, comment="标签数组")
    doc_type: Mapped[str] = mapped_column(String(16), default="markdown", comment="markdown|txt|docx|xlsx|web")
    file_path: Mapped[str | None] = mapped_column(String(255), default=None)
    word_count: Mapped[int] = mapped_column(Integer, default=0)

    # 向量化状态
    vector_status: Mapped[str] = mapped_column(String(16), default="pending",
                                               comment="pending|processing|done|failed")
    vector_count: Mapped[int] = mapped_column(Integer, default=0, comment="切片数量")
    vector_error: Mapped[str | None] = mapped_column(String(255), default=None)
    embedded_at: Mapped[str | None] = mapped_column(String(32), default=None)

    read_count: Mapped[int] = mapped_column(Integer, default=0, comment="被引用/阅读次数")

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="doc", cascade="all, delete-orphan")

    def to_dict(self, with_content: bool = False) -> dict:
        data = {
            "id": self.id,
            "folder_id": self.folder_id,
            "title": self.title,
            "tags": self.tags or [],
            "doc_type": self.doc_type,
            "word_count": self.word_count,
            "vector_status": self.vector_status,
            "vector_count": self.vector_count,
            "read_count": self.read_count,
            "summary": self.summary,
            "file_path": self.file_path,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }
        if with_content:
            data["content"] = self.content
        return data


class KnowledgeChunk(Base, TimestampMixin):
    """文档切片与向量（本地向量以 JSON 数组存储，可迁移到向量库）。"""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        Index("ix_kc_doc_index", "doc_id", "chunk_index"),
        {"comment": "知识库切片向量表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("knowledge_docs.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    content: Mapped[str] = mapped_column(LongText)
    embedding: Mapped[list] = mapped_column(JSON, default=list, comment="向量（float 数组）")
    dim: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0, comment="近似 token 数")
    score_cache: Mapped[float] = mapped_column(Float, default=0.0)

    doc: Mapped[KnowledgeDoc] = relationship(back_populates="chunks")

    def to_dict(self, with_embedding: bool = False) -> dict:
        data = {
            "id": self.id,
            "doc_id": self.doc_id,
            "chunk_index": self.chunk_index,
            "content": self.content,
            "dim": self.dim,
            "tokens": self.tokens,
        }
        if with_embedding:
            data["embedding"] = self.embedding
        return data
