from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class KnowledgeDoc(Base):
    """知识库文档：手动 Markdown 或上传解析后的文本，content 为可编辑正文。"""

    __tablename__ = "knowledge_docs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, index=True)
    title: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(16), default="manual")   # manual|upload
    file_type: Mapped[str] = mapped_column(String(16), default="md")    # md|txt|docx|xlsx
    file_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    read_count: Mapped[int] = mapped_column(Integer, default=0)         # 被 RAG 引用次数
    last_read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now, onupdate=datetime.now)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        "KnowledgeChunk", back_populates="doc", cascade="all, delete-orphan", lazy="dynamic"
    )

    def brief(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "source": self.source,
            "file_type": self.file_type,
            "file_url": self.file_url,
            "word_count": self.word_count,
            "tags": self.tags or [],
            "read_count": self.read_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class KnowledgeChunk(Base):
    """检索单元：入库时按滑窗切块，配合 rag.py 的 BM25 使用。"""

    __tablename__ = "knowledge_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    doc_id: Mapped[int] = mapped_column(ForeignKey("knowledge_docs.id", ondelete="CASCADE"), index=True)
    idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)

    doc: Mapped[KnowledgeDoc] = relationship(back_populates="chunks")
