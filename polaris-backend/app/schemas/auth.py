"""用户认证模块出入参。"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nickname: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    role: str = "user"
    is_active: bool = True
    wx_bound: bool = False
    config: dict = Field(default_factory=dict)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class RegisterIn(BaseModel):
    username: str = Field(min_length=2, max_length=64, description="登录名")
    password: str = Field(min_length=6, max_length=64)
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)

    @field_validator("username")
    @classmethod
    def _username_ok(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("用户名仅支持字母、数字、下划线、中划线")
        return v


class LoginIn(BaseModel):
    username: str
    password: str


class WxLoginIn(BaseModel):
    # code 允许缺省：开发环境 / 仿真环境下 wx.login 可能拿不到 code，
    # 此时后端用默认值派生稳定 openid，保证小程序开箱可用（生产会走真实 code2session）
    code: str = Field(default="mp-dev-static-code", max_length=256,
                      description="wx.login 返回的 code；缺省时使用开发用固定值")
    nickname: str | None = None
    avatar: str | None = None


class WxBindIn(BaseModel):
    code: str = Field(default="mp-dev-static-code", max_length=256,
                      description="wx.login code；开发模式由后端派生 openid")
    nickname: str | None = None


class UserUpdateIn(BaseModel):
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None


class UserConfigIn(BaseModel):
    config: dict = Field(default_factory=dict, description="用户配置项（主题色/提醒开关等）")
    merge: bool = Field(default=True, description="是否与已有配置合并")


class PasswordChangeIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=64)
