"""微信订阅消息路由：状态、配额上报、测试推送、扫描推送、推送日志。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.wechat import PushTestIn, QuotaGrantIn
from app.services import wechat_service

router = APIRouter(prefix="/wechat", tags=["⑬ 微信订阅消息"])


@router.get("/status", summary="订阅消息配置状态（是否已配置 AppID/模板/定时任务）")
def status(user: User = Depends(get_current_user)) -> dict:
    return wechat_service.status()


@router.get("/quota", summary="查询本用户剩余可推送次数（一次性订阅额度）")
def quota(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    items = wechat_service.quota_overview(db, user.id)
    return {"items": items,
            "total_remaining": sum(x["remaining"] for x in items),
            "wx_openid_bound": bool(user.wx_openid)}


@router.post("/subscribe/quota", summary="上报订阅授权次数（小程序授权成功后调用）")
def grant(body: QuotaGrantIn, db: Session = Depends(get_db),
          user: User = Depends(get_current_user)) -> dict:
    record = wechat_service.grant_quota(db, user.id, body.kind, body.times, body.template_id)
    return {"granted": True, "quota": record.to_dict(),
            "quota_all": wechat_service.quota_overview(db, user.id)}


@router.post("/push/test", summary="发送一条测试提醒（消耗一次配额）")
async def push_test(body: PushTestIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    context = {"title": body.title, "due_at": body.due_at, "category": body.category,
               "name": body.title, "start_time": body.due_at, "location": body.location}
    return await wechat_service.send(db, user, body.kind, context)


@router.post("/push/scan", summary="立即执行一次提醒扫描（到期任务 + 即将上课）")
async def scan(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return await wechat_service.run_scan(db)


@router.get("/push-logs", summary="推送日志（排查为什么没收到提醒）")
def logs(limit: int = Query(default=30, ge=1, le=200), db: Session = Depends(get_db),
         user: User = Depends(get_current_user)) -> dict:
    items = wechat_service.recent_logs(db, user.id, limit=limit)
    return {"total": len(items), "items": items}
