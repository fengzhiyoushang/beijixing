"""个人健康：记录 / 今日 / 周期报告 / 久坐设置与提醒心跳。"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas import HealthLogIn, HealthSettingIn, HeartbeatIn
from app.services.health_svc import get_or_create_settings, sedentary_status

router = APIRouter(prefix="/health", tags=["个人健康"])


@router.post("/logs", status_code=201)
def create_log(body: HealthLogIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    happened = body.happened_at or datetime.now()
    log = m.HealthLog(
        user_id=user.id, kind=body.kind, happened_at=happened,
        minutes=body.minutes, value=body.value, note=body.note, date=happened.date(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log.to_dict()


@router.get("/logs")
def list_logs(kind: str | None = Query(None), days: int = Query(30, ge=1, le=180),
              db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    q = db.query(m.HealthLog).filter(m.HealthLog.user_id == user.id,
                                     m.HealthLog.date >= date.today() - timedelta(days=days - 1))
    if kind:
        q = q.filter(m.HealthLog.kind == kind)
    return [r.to_dict() for r in q.order_by(m.HealthLog.id.desc()).limit(300).all()]


@router.get("/today")
def today(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    recs = (db.query(m.HealthLog)
            .filter(m.HealthLog.user_id == user.id, m.HealthLog.date == date.today())
            .order_by(m.HealthLog.id.desc()).all())
    return {"date": date.today().isoformat(),
            "logs": [r.to_dict() for r in recs],
            "sedentary": sedentary_status(db, user.id)}


@router.get("/report")
def report(days: int = Query(7, ge=1, le=90),
           db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    since = date.today() - timedelta(days=days - 1)
    logs = (db.query(m.HealthLog)
            .filter(m.HealthLog.user_id == user.id, m.HealthLog.date >= since).all())

    def by_kind(kind):
        return [l for l in logs if l.kind == kind]

    sleeps = by_kind("sleep")
    sleep_vals = [l.minutes for l in sleeps if l.minutes]
    daily = []
    for i in range(days):
        d = since + timedelta(days=i)
        day_logs = [l for l in logs if l.date == d]
        daily.append({
            "date": d.isoformat(),
            "sleep_minutes": sum(l.minutes or 0 for l in day_logs if l.kind == "sleep"),
            "water_ml": int(sum(l.value or 0 for l in day_logs if l.kind == "water")),
            "exercise_minutes": sum(l.minutes or 0 for l in day_logs if l.kind == "exercise"),
            "breaks": sum(1 for l in day_logs if l.kind == "sedentary"),
        })
    return {
        "days": days,
        "sleep": {
            "avg_minutes": int(sum(sleep_vals) / len(sleep_vals)) if sleep_vals else None,
            "records": len(sleep_vals),
            "shortage_days": sum(1 for v in sleep_vals if v < 7 * 60),
        },
        "exercise_minutes": sum(l.minutes or 0 for l in by_kind("exercise")),
        "water_total_ml": int(sum(l.value or 0 for l in by_kind("water"))),
        "sedentary_breaks": len(by_kind("sedentary")),
        "daily": daily,
        "sedentary_now": sedentary_status(db, user.id),
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    return get_or_create_settings(db, user.id).to_dict()


@router.put("/settings")
def update_settings(body: HealthSettingIn, db: Session = Depends(get_db),
                    user: m.User = Depends(get_current_user)):
    st = get_or_create_settings(db, user.id)
    for k, v in body.model_dump(exclude_unset=True).items():
        if v is not None:
            setattr(st, k, v)
    db.commit()
    db.refresh(st)
    return st.to_dict()


@router.post("/sedentary-heartbeat")
def heartbeat(body: HeartbeatIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    """双端定时轮询：返回是否应当起身活动。"""
    return sedentary_status(db, user.id)


@router.post("/sedentary-break")
def sedentary_break(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    """确认已完成起身活动，重置久坐计时并记录。"""
    st = get_or_create_settings(db, user.id)
    st.last_heartbeat_at = datetime.now()
    db.add(m.HealthLog(user_id=user.id, kind="sedentary", happened_at=datetime.now(),
                       date=date.today(), note="起身活动打卡"))
    db.commit()
    return sedentary_status(db, user.id)


@router.delete("/logs/{log_id}")
def delete_log(log_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    log = db.get(m.HealthLog, log_id)
    if not log or log.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    db.delete(log)
    db.commit()
    return {"deleted": log_id}
