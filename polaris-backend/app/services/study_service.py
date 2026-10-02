"""学习记录服务：录入、统计、模考、学习进度。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.study import StudyRecord


def get_record(db: Session, user_id: int, record_id: int) -> StudyRecord:
    record = db.get(StudyRecord, record_id)
    if not record or record.user_id != user_id:
        raise NotFoundError("学习记录不存在")
    return record


def list_records(db: Session, user_id: int, *, start: date | None = None, end: date | None = None,
                 subject: str | None = None, only_mock: bool = False,
                 limit: int = 200) -> list[StudyRecord]:
    query = db.query(StudyRecord).filter(StudyRecord.user_id == user_id)
    if start:
        query = query.filter(StudyRecord.date >= start)
    if end:
        query = query.filter(StudyRecord.date <= end)
    if subject:
        query = query.filter(StudyRecord.subject == subject)
    if only_mock:
        query = query.filter(StudyRecord.mock_score.isnot(None))
    return query.order_by(StudyRecord.date.desc(), StudyRecord.id.desc()).limit(limit).all()


def create_record(db: Session, user_id: int, payload) -> StudyRecord:
    record = StudyRecord(
        user_id=user_id,
        date=payload.date or date.today(),
        subject=payload.subject,
        minutes=payload.minutes,
        content=payload.content,
        mood=payload.mood,
        focus_score=payload.focus_score,
        task_id=payload.task_id,
        mock_name=payload.mock_name,
        mock_score=payload.mock_score,
        mock_full_score=payload.mock_full_score,
        started_at=payload.started_at,
        ended_at=payload.ended_at,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def update_record(db: Session, user_id: int, record_id: int, payload) -> StudyRecord:
    record = get_record(db, user_id, record_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


def delete_record(db: Session, user_id: int, record_id: int) -> None:
    record = get_record(db, user_id, record_id)
    db.delete(record)
    db.commit()


def add_mock_score(db: Session, user_id: int, payload) -> StudyRecord:
    """模考成绩录入（自动生成一条学习记录）。"""
    record = StudyRecord(
        user_id=user_id,
        date=payload.date or date.today(),
        subject=payload.subject,
        minutes=0,
        content=f"模考：{payload.mock_name}" + (f" | {payload.note}" if payload.note else ""),
        mock_name=payload.mock_name,
        mock_score=payload.score,
        mock_full_score=payload.full_score,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def stats(db: Session, user_id: int, days: int = 7) -> dict:
    """按天/科目聚合的统计，含连续打卡与模考记录。"""
    end = date.today()
    start = end - timedelta(days=days - 1)
    records = list_records(db, user_id, start=start, end=end, limit=1000)

    daily_map: dict[str, int] = {}
    focus_map: dict[str, list[int]] = {}
    for record in records:
        key = record.date.isoformat()
        daily_map[key] = daily_map.get(key, 0) + (record.minutes or 0)
        if record.focus_score:
            focus_map.setdefault(key, []).append(record.focus_score)

    daily = []
    for i in range(days):
        day = start + timedelta(days=i)
        minutes = daily_map.get(day.isoformat(), 0)
        focus = focus_map.get(day.isoformat()) or []
        daily.append({
            "date": day.isoformat(),
            "weekday": day.isoweekday(),
            "minutes": minutes,
            "hours": round(minutes / 60, 2),
            "focus_avg": round(sum(focus) / len(focus)) if focus else None,
        })

    subject_rows = (db.query(StudyRecord.subject, func.sum(StudyRecord.minutes),
                             func.count(StudyRecord.id))
                    .filter(StudyRecord.user_id == user_id, StudyRecord.date >= start,
                            StudyRecord.date <= end)
                    .group_by(StudyRecord.subject).all())
    by_subject = [{"subject": s, "minutes": int(m or 0), "hours": round((m or 0) / 60, 2),
                   "sessions": int(c)} for s, m, c in subject_rows]
    by_subject.sort(key=lambda x: -x["minutes"])

    total_minutes = sum(d["minutes"] for d in daily)
    active_days = sum(1 for d in daily if d["minutes"] > 0)

    # 连续打卡：从今天往前推；若今天尚未学习，则从昨天开始算（保留昨日连续记录）
    streak = 0
    cursor = end
    all_dates = {r.date for r in list_records(db, user_id, limit=2000)}
    if cursor not in all_dates:
        cursor -= timedelta(days=1)
    while cursor in all_dates:
        streak += 1
        cursor -= timedelta(days=1)

    mocks = [r.to_dict() for r in records if r.mock_score is not None]

    # 学习进度：任务完成
    from app.models.task import DdlTask

    tasks = db.query(DdlTask).filter(DdlTask.user_id == user_id).all()
    done_tasks = sum(1 for t in tasks if t.status == "done")

    return {
        "range": {"start": start.isoformat(), "end": end.isoformat(), "days": days},
        "total_minutes": total_minutes,
        "total_hours": round(total_minutes / 60, 2),
        "avg_minutes_per_day": round(total_minutes / days, 1),
        "avg_minutes_per_active_day": round(total_minutes / active_days, 1) if active_days else 0,
        "active_days": active_days,
        "streak_days": streak,
        "daily": daily,
        "by_subject": by_subject,
        "mock_scores": mocks[-10:],
        "task_progress": {
            "total": len(tasks),
            "done": done_tasks,
            "rate": round(done_tasks / len(tasks), 4) if tasks else 0,
        },
    }
