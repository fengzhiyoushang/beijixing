"""空教室：拍照标注采集（小程序）/ 历史查询 / 规律分析 / 空闲预测（Web）。"""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import get_db
from app.core.deps import get_current_user
from app.services import classroom as classroom_svc
from app.services.storage import save_upload

router = APIRouter(prefix="/classroom", tags=["空教室"])


@router.get("/records")
def list_records(
    building: str | None = Query(None),
    room: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
):
    q = db.query(m.ClassroomRecord).filter(m.ClassroomRecord.user_id == user.id)
    if building:
        q = q.filter(m.ClassroomRecord.building == building)
    if room:
        q = q.filter(m.ClassroomRecord.room == room)
    recs = q.order_by(m.ClassroomRecord.id.desc()).limit(limit).all()
    return [r.to_dict() for r in recs]


@router.post("/checkin", status_code=201)
async def checkin_room(
    building: str = Form(...),
    room: str = Form(...),
    occupied: int = Form(0, ge=0, le=1),
    note: str | None = Form(None),
    photo: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
):
    """小程序拍照标注入口：occupied 0=空闲 1=占用。"""
    photo_url = None
    if photo is not None:
        content = await photo.read()
        if content:
            photo_url = save_upload(content, photo.filename or "photo.jpg", "classroom")
    now = datetime.now()
    rec = m.ClassroomRecord(
        user_id=user.id, building=building, room=room, occupied=occupied,
        note=note, photo_url=photo_url, weekday=now.isoweekday(), hour=now.hour,
        visited_at=now,
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec.to_dict()


@router.get("/buildings")
def buildings(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    return classroom_svc.list_buildings(db, user.id)


@router.get("/pattern")
def pattern(
    building: str = Query(...),
    room: str = Query(...),
    db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
):
    return classroom_svc.room_pattern(db, user.id, building, room)


@router.get("/predict")
def predict(
    weekday: int | None = Query(None, ge=1, le=7),
    hour: int | None = Query(None, ge=0, le=23),
    db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
):
    """空闲预测：缺省按当前 weekday/hour。"""
    return classroom_svc.predict(db, user.id, weekday, hour)


@router.delete("/records/{rec_id}")
def delete_record(rec_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    rec = db.get(m.ClassroomRecord, rec_id)
    if not rec or rec.user_id != user.id:
        raise HTTPException(404, "记录不存在")
    db.delete(rec)
    db.commit()
    return {"deleted": rec_id}
