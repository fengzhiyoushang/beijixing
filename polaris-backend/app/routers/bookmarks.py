"""地址中心路由：常用网址书签 CRUD。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.models.bookmark import Bookmark
from app.models.user import User

router = APIRouter(prefix="/bookmarks", tags=["⑮ 地址中心"])


class BookmarkIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=4, max_length=500)
    category: str = Field(default="常用", max_length=32)
    note: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=8)
    color: str | None = Field(default=None, max_length=16)
    sort_order: int = 0


def _normalize_url(url: str) -> str:
    u = url.strip()
    if not u:
        raise AppError("链接不能为空")
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    return u


@router.get("", summary="书签列表（可按分类/关键词筛选）")
def list_bookmarks(category: str | None = Query(default=None),
                   keyword: str | None = Query(default=None),
                   db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    q = select(Bookmark).where(Bookmark.user_id == user.id)
    if category:
        q = q.where(Bookmark.category == category)
    if keyword:
        like = f"%{keyword}%"
        q = q.where(Bookmark.title.like(like) | Bookmark.note.like(like) | Bookmark.url.like(like))
    rows = db.execute(q.order_by(Bookmark.sort_order.asc(), Bookmark.id.desc())).scalars().all()
    cats = db.execute(
        select(Bookmark.category).where(Bookmark.user_id == user.id).distinct()
    ).scalars().all()
    return {"total": len(rows), "items": [r.to_dict() for r in rows], "categories": sorted(cats)}


@router.post("", summary="新增书签")
def create_bookmark(body: BookmarkIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    b = Bookmark(
        user_id=user.id, title=body.title.strip(), url=_normalize_url(body.url),
        category=body.category or "常用", note=body.note, icon=body.icon,
        color=body.color, sort_order=body.sort_order,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return b.to_dict()


@router.put("/{bid}", summary="更新书签")
def update_bookmark(bid: int, body: BookmarkIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    b = db.get(Bookmark, bid)
    if not b or b.user_id != user.id:
        raise AppError("书签不存在", status_code=404)
    b.title = body.title.strip()
    b.url = _normalize_url(body.url)
    b.category = body.category or "常用"
    b.note = body.note
    b.icon = body.icon
    b.color = body.color
    b.sort_order = body.sort_order
    db.commit()
    db.refresh(b)
    return b.to_dict()


@router.post("/{bid}/click", summary="记录一次打开（累加点击数）")
def click_bookmark(bid: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    b = db.get(Bookmark, bid)
    if not b or b.user_id != user.id:
        raise AppError("书签不存在", status_code=404)
    b.click_count = (b.click_count or 0) + 1
    db.commit()
    return {"id": b.id, "click_count": b.click_count}


@router.delete("/{bid}", summary="删除书签")
def delete_bookmark(bid: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    b = db.get(Bookmark, bid)
    if not b or b.user_id != user.id:
        raise AppError("书签不存在", status_code=404)
    db.delete(b)
    db.commit()
    return {"deleted": True, "id": bid}
