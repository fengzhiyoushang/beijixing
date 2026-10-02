"""① 用户表：账号密码、微信绑定、个人配置。"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, iso


class User(Base, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_username", "username", unique=True),
        Index("ix_users_wx_openid", "wx_openid", unique=True),
        {"comment": "用户表：账号、微信绑定、配置项"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, comment="登录名")
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="PBKDF2 哈希")
    nickname: Mapped[str | None] = mapped_column(String(64), default=None, comment="昵称")
    email: Mapped[str | None] = mapped_column(String(128), default=None)
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    avatar: Mapped[str | None] = mapped_column(String(255), default=None, comment="头像 URL/首字")
    role: Mapped[str] = mapped_column(String(16), default="user", comment="user | admin")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 微信绑定
    wx_openid: Mapped[str | None] = mapped_column(String(64), default=None, comment="小程序 openid")
    wx_unionid: Mapped[str | None] = mapped_column(String(64), default=None, comment="开放平台 unionid")
    wx_nickname: Mapped[str | None] = mapped_column(String(64), default=None)

    # 个人配置项（主题色、提醒开关、目标作息等）
    config: Mapped[dict] = mapped_column(JSON, default=dict, comment="用户配置 JSON")

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    def to_dict(self, with_sensitive: bool = False) -> dict:
        data = {
            "id": self.id,
            "username": self.username,
            "nickname": self.nickname,
            "email": self.email,
            "phone": self.phone,
            "avatar": self.avatar or (self.nickname or self.username or "北")[:1],
            "role": self.role,
            "is_active": self.is_active,
            "wx_bound": bool(self.wx_openid),
            "config": self.config or {},
            "last_login_at": iso(self.last_login_at),
            "created_at": iso(self.created_at),
        }
        if with_sensitive:
            data["wx_openid"] = self.wx_openid
            data["wx_unionid"] = self.wx_unionid
        return data
