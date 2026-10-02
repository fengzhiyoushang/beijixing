"""总览仪表盘路由：一次请求返回首页所需聚合数据。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["① 总览仪表盘"])


@router.get("/summary", summary="首页总览（课程/任务/学习/考研/知识/财务/健康/教室/提醒）")
def summary(days: int = Query(default=7, ge=1, le=90),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return dashboard_service.build_summary(db, user, days=days)


@router.get("/alerts", summary="仅取提醒列表（快讯头条）")
def alerts(days: int = Query(default=7, ge=1, le=90),
           db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    data = dashboard_service.build_summary(db, user, days=days)
    return {"total": len(data["alerts"]), "items": data["alerts"]}


@router.post("/cache/clear", summary="清除本用户总览缓存（数据批量变更后调用）")
def clear_cache(user: User = Depends(get_current_user)) -> dict:
    dashboard_service.invalidate(user.id)
    return {"cleared": True}
