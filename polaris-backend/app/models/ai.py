"""AI 会话与消息（Function Call 轨迹落库）+ Token 用量台账。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import LongText, TimestampMixin, iso


class AiSession(Base, TimestampMixin):
    __tablename__ = "ai_sessions"
    __table_args__ = (
        Index("ix_ai_sessions_user", "user_id", "updated_at"),
        {"comment": "AI 会话表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="新会话")
    channel: Mapped[str] = mapped_column(String(16), default="web", comment="web|miniapp")
    message_count: Mapped[int] = mapped_column(Integer, default=0)

    messages: Mapped[list["AiMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="AiMessage.id")

    def to_dict(self, with_messages: bool = False) -> dict:
        data = {
            "id": self.id,
            "title": self.title,
            "channel": self.channel,
            "message_count": self.message_count,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }
        if with_messages:
            data["messages"] = [m.to_dict() for m in self.messages]
        return data


class AiMessage(Base, TimestampMixin):
    __tablename__ = "ai_messages"
    __table_args__ = (
        Index("ix_ai_messages_session", "session_id", "id"),
        {"comment": "AI 消息表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("ai_sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16), comment="user|assistant|tool|system")
    content: Mapped[str | None] = mapped_column(LongText, default=None)
    tool_calls: Mapped[list] = mapped_column(JSON, default=list, comment="模型请求调用的工具")
    tool_name: Mapped[str | None] = mapped_column(String(64), default=None, comment="tool 角色时的工具名")
    tokens: Mapped[int] = mapped_column(Integer, default=0, comment="本条消息折算 token（估算值，权威用量见 ai_usage）")

    session: Mapped[AiSession] = relationship(back_populates="messages")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "tool_calls": self.tool_calls or [],
            "tool_name": self.tool_name,
            "created_at": iso(self.created_at),
        }


class AiUsage(Base):
    """Token 用量台账：每次真实调用记一行（provider 返回的 usage 原样落库）。"""
    __tablename__ = "ai_usage"
    __table_args__ = (
        Index("ix_ai_usage_user_time", "user_id", "created_at"),
        {"comment": "AI 调用 token 用量（真实计数，供顶部消耗/剩余展示）"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    session_id: Mapped[int | None] = mapped_column(Integer, default=None)
    model: Mapped[str] = mapped_column(String(80), default="")
    provider: Mapped[str] = mapped_column(String(40), default="deepseek")
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0)
    estimated: Mapped[bool] = mapped_column(Boolean, default=False, comment="provider 未返回 usage 时为估算")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "model": self.model,
            "provider": self.provider,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated": self.estimated,
            "created_at": iso(self.created_at),
        }
