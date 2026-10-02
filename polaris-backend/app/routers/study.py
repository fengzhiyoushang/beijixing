"""学习记录路由：录入、统计、模考成绩、学习进度。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.study import MockScoreIn, StudyRecordIn, StudyRecordUpdate
from app.services import study_service

router = APIRouter(prefix="/study", tags=["⑥ 学习记录"])


@router.get("/stats", summary="学习统计（按时长/科目/模考/连续打卡）")
def stats(days: int = Query(default=7, ge=1, le=365), db: Session = Depends(get_db),
          user: User = Depends(get_current_user)) -> dict:
    return study_service.stats(db, user.id, days=days)


@router.get("/progress", summary="学习进度总览（时长 + 任务完成率）")
def progress(days: int = Query(default=7, ge=1, le=365), db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    data = study_service.stats(db, user.id, days=days)
    return {
        "days": days,
        "total_hours": data["total_hours"],
        "avg_minutes_per_day": data["avg_minutes_per_day"],
        "streak_days": data["streak_days"],
        "active_days": data["active_days"],
        "by_subject": data["by_subject"],
        "task_progress": data["task_progress"],
        "daily": data["daily"],
    }


@router.get("/records", summary="学习记录列表")
def list_records(start: date | None = Query(default=None), end: date | None = Query(default=None),
                 subject: str | None = Query(default=None),
                 only_mock: bool = Query(default=False),
                 limit: int = Query(default=200, ge=1, le=1000),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    records = study_service.list_records(db, user.id, start=start, end=end, subject=subject,
                                         only_mock=only_mock, limit=limit)
    return {"total": len(records), "items": [r.to_dict() for r in records]}


@router.post("/records", summary="新增学习记录")
def create_record(body: StudyRecordIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    record = study_service.create_record(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return record.to_dict()


@router.put("/records/{record_id}", summary="更新学习记录")
def update_record(record_id: int, body: StudyRecordUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    record = study_service.update_record(db, user.id, record_id, body)
    dashboard_service.invalidate(user.id)
    return record.to_dict()


@router.delete("/records/{record_id}", summary="删除学习记录")
def delete_record(record_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    study_service.delete_record(db, user.id, record_id)
    dashboard_service.invalidate(user.id)
    return {"deleted": True}


@router.post("/mock-scores", summary="录入模考成绩")
def add_mock(body: MockScoreIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    record = study_service.add_mock_score(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return record.to_dict()


@router.get("/mock-scores", summary="模考成绩列表")
def list_mocks(limit: int = Query(default=30, ge=1, le=200), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    records = study_service.list_records(db, user.id, only_mock=True, limit=limit)
    items = [r.to_dict() for r in records]
    by_subject: dict[str, list] = {}
    for item in items:
        by_subject.setdefault(item["subject"], []).append(item)
    return {"total": len(items), "items": items,
            "by_subject": [{"subject": k, "scores": [x["mock_score"] for x in v][::-1],
                            "latest": v[0]["mock_score"], "count": len(v)}
                           for k, v in by_subject.items()]}
