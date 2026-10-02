"""FastAPI 依赖：数据库会话、当前用户、分页参数。"""
from __future__ import annotations

from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import AuthError
from app.core.security import decode_token
from app.models.user import User


def get_token(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError("缺少 Bearer Token")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(token: str = Depends(get_token), db: Session = Depends(get_db)) -> User:
    payload = decode_token(token)
    if not payload:
        raise AuthError("Token 无效或已过期")
    user = db.get(User, int(payload.get("sub", 0)))
    if not user:
        raise AuthError("用户不存在")
    if not user.is_active:
        raise AuthError("账号已被禁用", status_code=403)
    return user


def get_optional_user(authorization: str | None = Header(default=None),
                      db: Session = Depends(get_db)) -> User | None:
    """可选登录：用于公开接口但携带身份时可个性化。"""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    payload = decode_token(authorization.split(" ", 1)[1].strip())
    if not payload:
        return None
    return db.get(User, int(payload.get("sub", 0)))


class PageParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="页码，从 1 开始"),
        page_size: int = Query(20, ge=1, le=200, description="每页条数"),
    ):
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        return self.page_size


def paginate(query, params: PageParams) -> dict:
    """对 SQLAlchemy 查询做分页，返回统一结构。"""
    total = query.order_by(None).count()
    items = query.offset(params.offset).limit(params.limit).all()
    pages = (total + params.page_size - 1) // params.page_size if params.page_size else 0
    return {
        "items": items,
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "pages": pages,
    }
