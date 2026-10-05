"""新闻资讯路由：抓取（后台执行）、列表、详情、已读/收藏、源管理、抓取日志。"""
from __future__ import annotations

import asyncio
from datetime import datetime
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db, session_scope
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.models.news import NewsSource
from app.models.user import User
from app.services import news_service

router = APIRouter(prefix="/news", tags=["⑯ 新闻资讯"])

# 抓取互斥：同一时刻只允许一轮抓取在跑（保护源站，符合限速准则）
_crawl_lock = asyncio.Lock()
_crawl_state: dict = {"running": False, "last_result": None}


# ─────────── 列表与详情 ───────────
@router.get("/items", summary="新闻列表（分类/关键词/未读/收藏筛选 + 分页）")
def list_items(category: str | None = Query(default=None),
               keyword: str | None = Query(default=None),
               unread_only: bool = Query(default=False),
               starred_only: bool = Query(default=False),
               limit: int = Query(default=30, ge=1, le=100),
               offset: int = Query(default=0, ge=0),
               db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    news_service.ensure_default_sources(db)
    return news_service.list_items(db, category=category, keyword=keyword,
                                   unread_only=unread_only, starred_only=starred_only,
                                   limit=limit, offset=offset)


@router.get("/categories", summary="分类统计")
def list_categories(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    return {"items": news_service.categories(db)}


@router.get("/items/{item_id}", summary="新闻详情（含聚焦抓取的正文）")
def item_detail(item_id: int, mark_read: bool = Query(default=True),
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    item = news_service.get_item(db, item_id)
    if not item:
        raise AppError("文章不存在", status_code=404)
    if mark_read and not item.is_read:
        item.is_read = True
        db.commit()
    return item.to_dict(with_content=True)


@router.post("/items/{item_id}/read", summary="标记已读/未读")
def set_read(item_id: int, is_read: bool = Query(default=True),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    item = news_service.get_item(db, item_id)
    if not item:
        raise AppError("文章不存在", status_code=404)
    item.is_read = is_read
    db.commit()
    return {"id": item.id, "is_read": item.is_read}


@router.post("/items/{item_id}/star", summary="收藏/取消收藏")
def set_star(item_id: int, is_starred: bool = Query(default=True),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    item = news_service.get_item(db, item_id)
    if not item:
        raise AppError("文章不存在", status_code=404)
    item.is_starred = is_starred
    db.commit()
    return {"id": item.id, "is_starred": item.is_starred}


@router.delete("/items/{item_id}", summary="删除文章")
def remove_item(item_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    item = news_service.get_item(db, item_id)
    if not item:
        raise AppError("文章不存在", status_code=404)
    db.delete(item)
    db.commit()
    return {"deleted": True, "id": item_id}


# ─────────── 抓取 ───────────
async def _run_crawl(force: bool) -> None:
    async with _crawl_lock:
        _crawl_state["running"] = True
        try:
            with session_scope() as db:
                result = await news_service.crawl_all(db, force=force)
            _crawl_state["last_result"] = {**result, "finished_at": datetime.now().strftime("%H:%M:%S")}
        except Exception as exc:  # noqa: BLE001
            _crawl_state["last_result"] = {"error": str(exc)[:300]}
        finally:
            _crawl_state["running"] = False


@router.post("/crawl", summary="触发抓取（后台执行：通用→增量→聚焦）")
async def crawl(force: bool = Query(default=False)) -> dict:
    if _crawl_state["running"]:
        return {"started": False, "reason": "已有抓取任务在运行", "state": _crawl_state}
    asyncio.create_task(_run_crawl(force))
    return {"started": True, "hint": "后台抓取中，稍后刷新列表查看新内容"}


@router.get("/crawl/status", summary="抓取状态与结果")
def crawl_status() -> dict:
    return _crawl_state


@router.get("/logs", summary="最近抓取日志")
def crawl_logs(limit: int = Query(default=10, ge=1, le=50),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"items": news_service.recent_logs(db, limit=limit)}


# ─────────── 源管理 ───────────
class SourceIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=6, max_length=500)
    category: str = Field(default="综合", max_length=24)
    mode: str = Field(default="rss", pattern="^(rss|json|focused)$")
    enabled: bool = True
    interval_min: int = Field(default=30, ge=5, le=1440)


@router.get("/sources", summary="抓取源列表")
def list_sources(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    news_service.ensure_default_sources(db)
    rows = db.execute(select(NewsSource).order_by(NewsSource.category, NewsSource.id)).scalars().all()
    return {"items": [r.to_dict() for r in rows]}


@router.post("/sources", summary="新增抓取源")
def create_source(body: SourceIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    exists = db.execute(select(NewsSource).where(NewsSource.url == body.url)).scalar_one_or_none()
    if exists:
        raise AppError("该源地址已存在")
    s = NewsSource(**body.model_dump())
    db.add(s)
    db.commit()
    db.refresh(s)
    return s.to_dict()


@router.put("/sources/{sid}", summary="更新抓取源")
def update_source(sid: int, body: SourceIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    s = db.get(NewsSource, sid)
    if not s:
        raise AppError("源不存在", status_code=404)
    for k, v in body.model_dump().items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return s.to_dict()


@router.delete("/sources/{sid}", summary="删除抓取源")
def delete_source(sid: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    s = db.get(NewsSource, sid)
    if not s:
        raise AppError("源不存在", status_code=404)
    db.delete(s)
    db.commit()
    return {"deleted": True, "id": sid}


# ─────────── 图片代理（解决外链防盗链导致的图片无法渲染） ───────────
_IMG_MAX_BYTES = 5 * 1024 * 1024


@router.get("/image", summary="新闻配图代理（绕过源站 Referer 防盗链；img 标签无法带 JWT，故公开）")
async def image_proxy(url: str = Query(min_length=10)) -> Response:
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise AppError("仅支持 http/https 图片", status_code=400)
    host = (parsed.hostname or "").lower()
    if not host or host in ("localhost", "127.0.0.1", "0.0.0.0", "::1") or host.startswith("192.168.") \
            or host.startswith("10.") or host.startswith("172.16."):
        raise AppError("不允许的内网地址", status_code=400)
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            # 带源站 Referer 请求，兼容按 Referer 白名单放行的图床
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": f"{parsed.scheme}://{parsed.netloc}/",
            }
            resp = await client.get(url.strip(), headers=headers)
            resp.raise_for_status()
    except Exception as exc:  # noqa: BLE001
        raise AppError(f"图片获取失败：{type(exc).__name__}", status_code=404)
    ctype = resp.headers.get("content-type", "")
    if not ctype.startswith("image/"):
        raise AppError("目标不是图片", status_code=400)
    data = resp.content
    if len(data) > _IMG_MAX_BYTES:
        raise AppError("图片过大", status_code=413)
    return Response(
        content=data, media_type=ctype.split(";")[0],
        headers={"Cache-Control": "public, max-age=86400"},
    )
