"""用户认证路由：注册/登录/微信绑定/个人资料/配置。"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppError, AuthError, ConflictError
from app.core.security import (create_access_token, derive_wx_openid, hash_password,
                               verify_password)
from app.models.user import User
from app.schemas.auth import (LoginIn, PasswordChangeIn, RegisterIn, TokenOut, UserConfigIn,
                              UserOut, UserUpdateIn, WxBindIn, WxLoginIn)

router = APIRouter(prefix="/auth", tags=["① 用户认证"])


def _issue(user: User) -> dict:
    token = create_access_token(user.id, extra={"username": user.username})
    user.last_login_at = datetime.now()
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        "user": user.to_dict(),
    }


@router.post("/register", response_model=None, summary="注册（用户名 + 密码）")
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    exists = db.query(User).filter(User.username == body.username).first()
    if exists:
        raise ConflictError(f"用户名 {body.username} 已被占用")
    user = User(
        username=body.username,
        password_hash=hash_password(body.password),
        nickname=body.nickname or body.username,
        email=body.email,
        phone=body.phone,
        config={"theme": "dark", "accent": "#4ade80", "school": "华中科技大学", "role": "考研备战中"},
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue(user)


@router.post("/login", summary="账号密码登录 → JWT")
def login(body: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise AuthError("用户名或密码错误")
    if not user.is_active:
        raise AuthError("账号已被禁用", status_code=403)
    result = _issue(user)
    db.commit()
    return result


@router.post("/wx-login", summary="微信小程序登录（code → openid，开发模式自动派生）")
def wx_login(body: WxLoginIn, db: Session = Depends(get_db)) -> dict:
    openid = derive_wx_openid(body.code)
    user = db.query(User).filter(User.wx_openid == openid).first()
    if not user:
        user = User(
            username=f"wx_{openid[-10:]}",
            nickname=body.nickname or "小程序同学",
            avatar=body.avatar,
            wx_openid=openid,
            config={"theme": "dark", "accent": "#4ade80", "channel": "miniapp"},
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return _issue(user)


@router.post("/wx/bind", summary="把当前账号与微信 openid 绑定（双端同数据）")
def wx_bind(body: WxBindIn, user: User = Depends(get_current_user),
            db: Session = Depends(get_db)) -> dict:
    openid = derive_wx_openid(body.code)
    occupied = db.query(User).filter(User.wx_openid == openid, User.id != user.id).first()
    if occupied:
        raise ConflictError("该微信已绑定其它账号")
    user.wx_openid = openid
    user.wx_nickname = body.nickname or user.wx_nickname
    db.commit()
    db.refresh(user)
    return {"bound": True, "user": user.to_dict(with_sensitive=True)}


@router.get("/me", summary="获取当前用户信息")
def me(user: User = Depends(get_current_user)) -> dict:
    return user.to_dict()


@router.put("/me", summary="更新个人资料")
def update_me(body: UserUpdateIn, user: User = Depends(get_current_user),
              db: Session = Depends(get_db)) -> dict:
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(user, key, value)
    db.commit()
    db.refresh(user)
    return user.to_dict()


@router.put("/me/config", summary="更新用户配置项（合并或覆盖）")
def update_config(body: UserConfigIn, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)) -> dict:
    if body.merge:
        merged = dict(user.config or {})
        merged.update(body.config or {})
        user.config = merged
    else:
        user.config = body.config or {}
    db.commit()
    db.refresh(user)
    return {"config": user.config}


@router.post("/change-password", summary="修改密码")
def change_password(body: PasswordChangeIn, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)) -> dict:
    if body.old_password == body.new_password:
        raise AppError("新密码不能与旧密码相同")
    if user.password_hash and not verify_password(body.old_password, user.password_hash):
        raise AuthError("旧密码错误")
    user.password_hash = hash_password(body.new_password)
    db.commit()
    return {"changed": True}
