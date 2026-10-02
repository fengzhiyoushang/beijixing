"""健康路由：记录（按日 upsert）、报告、设置、久坐心跳与打断。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.health import HealthRecordIn, HealthRecordUpdate, HealthSettingIn, HeartbeatIn
from app.services import health_service

router = APIRouter(prefix="/health", tags=["⑩ 健康"])


# ─────────── 报告与设置（置于 /records/{id} 之前） ───────────
@router.get("/report", summary="健康报告（睡眠/运动/久坐/体重/建议）")
def report(days: int = Query(default=7, ge=1, le=365), db: Session = Depends(get_db),
           user: User = Depends(get_current_user)) -> dict:
    return health_service.report(db, user.id, days=days)


@router.get("/settings", summary="获取健康设置")
def get_settings(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return health_service.get_or_create_settings(db, user.id).to_dict()


@router.put("/settings", summary="更新健康设置（久坐间隔/免打扰/目标值）")
def update_settings(body: HealthSettingIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    return health_service.update_settings(db, user.id, body).to_dict()


@router.get("/sedentary", summary="当前久坐状态")
def sedentary(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return health_service.sedentary_status(db, user.id)


@router.post("/sedentary/heartbeat", summary="心跳上报（前端定时调用，用于久坐计时）")
def heartbeat(body: HeartbeatIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> dict:
    return health_service.heartbeat(db, user.id, spent_minutes=body.spent_minutes)


@router.post("/sedentary/break", summary="已起身：重置久坐计时并累计")
def take_break(body: HeartbeatIn | None = None, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    note = body.note if body else None
    return health_service.take_break(db, user.id, note=note)


# ─────────── 记录 ───────────
@router.get("/records", summary="健康记录列表（近 N 天）")
def list_records(days: int = Query(default=7, ge=1, le=365), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    records = health_service.list_records(db, user.id, days=days)
    return {"total": len(records), "items": [r.to_dict() for r in records]}


@router.post("/records", summary="录入健康数据（按日期 upsert，运动/饮水/步数累加）")
def upsert_record(body: HealthRecordIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    record = health_service.upsert_record(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return record.to_dict()


@router.put("/records/{record_id}", summary="修改健康记录")
def update_record(record_id: int, body: HealthRecordUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    record = health_service.update_record(db, user.id, record_id, body)
    dashboard_service.invalidate(user.id)
    return record.to_dict()


@router.delete("/records/{record_id}", summary="删除健康记录")
def delete_record(record_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    health_service.delete_record(db, user.id, record_id)
    dashboard_service.invalidate(user.id)
    return {"deleted": True}
