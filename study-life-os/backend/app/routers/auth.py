"""认证：注册 / 登录 / me / 微信小程序 wx-login（code2session，未配 AppID 走开发模式）。"""
import hashlib

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.schemas import LoginIn, RegisterIn, WxLoginIn

router = APIRouter(prefix="/auth", tags=["认证"])


def _issue_token(user: User) -> dict:
    return {"access_token": create_access_token(user.id, user.username),
            "token_type": "bearer", "user": user.to_dict()}


@router.post("/register", status_code=201)
def register(body: RegisterIn, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(409, "用户名已存在")
    user = User(
        username=body.username,
        nickname=body.nickname or body.username,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login")
def login(body: LoginIn, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not user.password_hash or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "用户名或密码错误")
    return _issue_token(user)


@router.get("/me")
def me(current: User = Depends(get_current_user)):
    return current.to_dict()


@router.post("/wx-login")
async def wx_login(body: WxLoginIn, db: Session = Depends(get_db)):
    """小程序登录：配置了 WX_APPID/SECRET 走 code2session，否则用 code 派生开发 openid。"""
    if settings.WX_APPID and settings.WX_SECRET:
        url = ("https://api.weixin.qq.com/sns/jscode2session"
               f"?appid={settings.WX_APPID}&secret={settings.WX_SECRET}"
               f"&js_code={body.code}&grant_type=authorization_code")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url)
        data = resp.json()
        openid = data.get("openid")
        if not openid:
            raise HTTPException(400, f"微信登录失败: {data.get('errmsg', '未知错误')}")
    else:
        openid = "dev_" + hashlib.sha1(body.code.encode()).hexdigest()[:16]

    user = db.query(User).filter(User.wx_openid == openid).first()
    if user is None:
        user = User(
            username=f"wx_{openid[-10:]}",
            nickname=body.nickname or "小程序同学",
            wx_openid=openid,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    return _issue_token(user)
