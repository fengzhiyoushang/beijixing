"""微信订阅消息：授权配额与推送日志。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, iso


class WxSubscriptionQuota(Base, TimestampMixin):
    """一次性订阅消息配额：用户每授权一次 +1，推送一次 -1。

    注意：微信个人主体小程序只能用「一次性订阅」，即用户授权几次就只能推几条，
    因此必须精确记账，避免无谓调用导致 43101（user refuse to accept the msg）。
    """

    __tablename__ = "wx_subscription_quotas"
    __table_args__ = (
        UniqueConstraint("user_id", "template_id", name="uq_wx_quota_user_template"),
        Index("ix_wx_quota_user_kind", "user_id", "kind"),
        {"comment": "微信订阅消息授权配额表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    template_id: Mapped[str] = mapped_column(String(64), comment="订阅消息模板 ID")
    kind: Mapped[str] = mapped_column(String(16), default="ddl", comment="ddl | class")
    granted_total: Mapped[int] = mapped_column(Integer, default=0, comment="累计授权次数")
    used_total: Mapped[int] = mapped_column(Integer, default=0, comment="累计已推送次数")
    remaining: Mapped[int] = mapped_column(Integer, default=0, comment="剩余可推送次数")
    last_granted_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    note: Mapped[str | None] = mapped_column(Text, default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "template_id": self.template_id,
            "granted_total": self.granted_total,
            "used_total": self.used_total,
            "remaining": self.remaining,
            "last_granted_at": iso(self.last_granted_at),
            "last_used_at": iso(self.last_used_at),
        }


class WxPushLog(Base, TimestampMixin):
    """推送日志（含去重键，避免同一任务重复轰炸）。"""

    __tablename__ = "wx_push_logs"
    __table_args__ = (
        Index("ix_wx_push_user_kind", "user_id", "kind", "created_at"),
        Index("ix_wx_push_dedup", "user_id", "dedup_key"),
        {"comment": "微信订阅消息推送日志表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default="ddl")
    template_id: Mapped[str | None] = mapped_column(String(64), default=None)
    openid: Mapped[str | None] = mapped_column(String(64), default=None)
    page: Mapped[str | None] = mapped_column(String(128), default=None, comment="点击跳转页面")
    payload: Mapped[dict] = mapped_column(JSON, default=dict, comment="模板数据")
    dedup_key: Mapped[str | None] = mapped_column(String(64), default=None, comment="去重键")
    status: Mapped[str] = mapped_column(String(24), default="success",
                                        comment="success|failed|skipped_no_quota|skipped_not_configured|skipped_duplicate|skipped_no_openid")
    errcode: Mapped[int | None] = mapped_column(Integer, default=None)
    errmsg: Mapped[str | None] = mapped_column(String(255), default=None)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "template_id": self.template_id,
            "page": self.page,
            "payload": self.payload or {},
            "dedup_key": self.dedup_key,
            "status": self.status,
            "errcode": self.errcode,
            "errmsg": self.errmsg,
            "created_at": iso(self.created_at),
        }
