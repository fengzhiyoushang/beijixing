"""学习打卡：录入 / 今日 / 月历 / 统计。"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import get_db
from app.core.deps import get_current_user
from app.services.dashboard import checkin_stats
from app.schemas import CheckinIn
from app.utils.timeutil import parse_month

router = APIRouter(prefix="/checkin", tags=["学习打卡"])


@router.post("", status_code=201)
def create_checkin(body: CheckinIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    rec = m.CheckinRecord(
        user_id=user.id, subject=body.subject, minutes=body.minutes,
        content=body.content, mood=body.mood, date=body.date or date.today(),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.to_dict()


@router.get("/today")
def today(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    recs = (
        db.query(m.CheckinRecord)
        .filter(m.CheckinRecord.user_id == user.id, m.CheckinRecord.date == date.today())
        .order_by(m.CheckinRecord.id.desc())
        .all()
    )
    return {"date": date.today().isoformat(),
            "total_minutes": sum(r.minutes for r in recs),
            "records": [r.to_dict() for r in recs]}


@router.get("/calendar")
def calendar(month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
             db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    start, end = parse_month(month)
    recs = (
        db.query(m.CheckinRecord)
        .filter(m.CheckinRecord.user_id == user.id,
                m.CheckinRecord.date >= start, m.CheckinRecord.date < end)
        .all()
    )
    days: dict[str, dict] = {}
    for r in recs:
        key = r.date.isoformat()
        d = days.setdefault(key, {"date": key, "minutes": 0, "count": 0, "subjects": []})
        d["minutes"] += r.minutes
        d["count"] += 1
        if r.subject not in d["subjects"]:
            d["subjects"].append(r.subject)
    return {"month": month, "days": days,
            "total_minutes": sum(d["minutes"] for d in days.values())}


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    return checkin_stats(db, user.id)


@router.delete("/{rec_id}")
def delete_checkin(rec_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    rec = db.get(m.CheckinRecord, rec_id)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    db.delete(rec)
    db.commit()
    return {"deleted": rec_id}
