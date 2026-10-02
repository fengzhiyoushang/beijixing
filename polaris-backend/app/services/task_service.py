"""DDL 任务服务：CRUD、子任务、统计、临近提醒。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.task import DdlTask, SubTask

PRIORITY_WEIGHT = {"high": 0, "medium": 1, "low": 2}


def get_task(db: Session, user_id: int, task_id: int) -> DdlTask:
    task = db.get(DdlTask, task_id)
    if not task or task.user_id != user_id:
        raise NotFoundError("任务不存在")
    return task


def list_tasks(
    db: Session,
    user_id: int,
    *,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    keyword: str | None = None,
    due_before: datetime | None = None,
    due_after: datetime | None = None,
    course_id: int | None = None,
    order: str = "due",
) -> list[DdlTask]:
    query = db.query(DdlTask).filter(DdlTask.user_id == user_id)
    if status:
        query = query.filter(DdlTask.status == status)
    if category:
        query = query.filter(DdlTask.category == category)
    if priority:
        query = query.filter(DdlTask.priority == priority)
    if course_id:
        query = query.filter(DdlTask.course_id == course_id)
    if keyword:
        query = query.filter(DdlTask.title.like(f"%{keyword}%"))
    if due_before:
        query = query.filter(DdlTask.due_at <= due_before)
    if due_after:
        query = query.filter(DdlTask.due_at >= due_after)

    if order == "created":
        query = query.order_by(DdlTask.created_at.desc())
    elif order == "priority":
        query = query.order_by(DdlTask.due_at.is_(None), DdlTask.due_at)
    else:
        query = query.order_by(DdlTask.due_at.is_(None), DdlTask.due_at)

    tasks = query.all()
    if order == "priority":
        tasks.sort(key=lambda t: (t.status != "pending", PRIORITY_WEIGHT.get(t.priority, 1),
                                  t.due_at or datetime.max))
    return tasks


def create_task(db: Session, user_id: int, payload) -> DdlTask:
    task = DdlTask(
        user_id=user_id,
        title=payload.title,
        description=payload.description,
        category=payload.category,
        priority=payload.priority,
        due_at=payload.due_at,
        remind_at=payload.remind_at,
        tags=payload.tags or [],
        estimate_minutes=payload.estimate_minutes,
        course_id=payload.course_id,
        source=getattr(payload, "source", "web") or "web",
    )
    db.add(task)
    db.flush()
    for i, sub in enumerate(payload.subtasks or []):
        db.add(SubTask(task_id=task.id, title=sub.title, is_done=sub.is_done,
                       sort_order=sub.sort_order or i, note=sub.note))
    db.commit()
    db.refresh(task)
    return task


def update_task(db: Session, user_id: int, task_id: int, payload) -> DdlTask:
    task = get_task(db, user_id, task_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(task, key, value)
    db.commit()
    db.refresh(task)
    return task


def complete_task(db: Session, user_id: int, task_id: int, *, done: bool = True) -> DdlTask:
    task = get_task(db, user_id, task_id)
    task.status = "done" if done else "pending"
    task.completed_at = datetime.now() if done else None
    if done:
        for sub in task.subtasks:
            sub.is_done = True
    db.commit()
    db.refresh(task)
    return task


def delete_task(db: Session, user_id: int, task_id: int) -> None:
    task = get_task(db, user_id, task_id)
    db.delete(task)
    db.commit()


# ─────────── 子任务 ───────────
def add_subtask(db: Session, user_id: int, task_id: int, payload) -> SubTask:
    task = get_task(db, user_id, task_id)
    sub = SubTask(task_id=task.id, title=payload.title, is_done=payload.is_done,
                  sort_order=payload.sort_order or len(task.subtasks), note=payload.note)
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def get_subtask(db: Session, user_id: int, subtask_id: int) -> SubTask:
    sub = db.get(SubTask, subtask_id)
    if not sub or not sub.task or sub.task.user_id != user_id:
        raise NotFoundError("子任务不存在")
    return sub


def update_subtask(db: Session, user_id: int, subtask_id: int, payload) -> SubTask:
    sub = get_subtask(db, user_id, subtask_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(sub, key, value)
    db.commit()
    db.refresh(sub)
    return sub


def delete_subtask(db: Session, user_id: int, subtask_id: int) -> None:
    sub = get_subtask(db, user_id, subtask_id)
    db.delete(sub)
    db.commit()


# ─────────── 统计 ───────────
def stats(db: Session, user_id: int, days: int = 7) -> dict:
    now = datetime.now()
    today_start = datetime.combine(date.today(), datetime.min.time())
    tomorrow = today_start + timedelta(days=1)

    base = db.query(DdlTask).filter(DdlTask.user_id == user_id)
    total = base.count()
    pending = base.filter(DdlTask.status == "pending").count()
    done = base.filter(DdlTask.status == "done").count()
    archived = base.filter(DdlTask.status == "archived").count()

    overdue = base.filter(DdlTask.status == "pending", DdlTask.due_at.isnot(None),
                          DdlTask.due_at < now).count()
    due_today = base.filter(DdlTask.status == "pending", DdlTask.due_at >= today_start,
                            DdlTask.due_at < tomorrow).count()
    due_week = base.filter(DdlTask.status == "pending", DdlTask.due_at >= today_start,
                           DdlTask.due_at < today_start + timedelta(days=7)).count()

    by_priority = dict(
        db.query(DdlTask.priority, func.count(DdlTask.id))
        .filter(DdlTask.user_id == user_id, DdlTask.status == "pending")
        .group_by(DdlTask.priority).all()
    )
    by_category = dict(
        db.query(DdlTask.category, func.count(DdlTask.id))
        .filter(DdlTask.user_id == user_id)
        .group_by(DdlTask.category).all()
    )

    # 近 N 天完成 / 新建趋势
    trend = []
    for i in range(days - 1, -1, -1):
        day = date.today() - timedelta(days=i)
        start = datetime.combine(day, datetime.min.time())
        end = start + timedelta(days=1)
        created = base.filter(DdlTask.created_at >= start, DdlTask.created_at < end).count()
        finished = db.query(DdlTask).filter(
            DdlTask.user_id == user_id, DdlTask.completed_at >= start,
            DdlTask.completed_at < end).count()
        trend.append({"date": day.isoformat(), "created": created, "done": finished})

    # 按时完成率（已完成的里，在截止时间前完成的比例）
    finished_tasks = base.filter(DdlTask.status == "done", DdlTask.due_at.isnot(None),
                                 DdlTask.completed_at.isnot(None)).all()
    on_time = sum(1 for t in finished_tasks if t.completed_at <= t.due_at)

    return {
        "total": total,
        "pending": pending,
        "done": done,
        "archived": archived,
        "overdue": overdue,
        "due_today": due_today,
        "due_week": due_week,
        "completion_rate": round(done / total, 4) if total else 0,
        "on_time_rate": round(on_time / len(finished_tasks), 4) if finished_tasks else None,
        "by_priority": {"high": by_priority.get("high", 0), "medium": by_priority.get("medium", 0),
                        "low": by_priority.get("low", 0)},
        "by_category": [{"category": k, "count": v} for k, v in sorted(by_category.items(), key=lambda x: -x[1])],
        "trend": trend,
    }


def upcoming(db: Session, user_id: int, within_days: int = 7, limit: int = 20) -> list[DdlTask]:
    now = datetime.now()
    end = now + timedelta(days=within_days)
    return (db.query(DdlTask)
            .filter(DdlTask.user_id == user_id, DdlTask.status == "pending",
                    DdlTask.due_at.isnot(None), DdlTask.due_at <= end)
            .order_by(DdlTask.due_at)
            .limit(limit).all())


def today_due(db: Session, user_id: int) -> list[DdlTask]:
    start = datetime.combine(date.today(), datetime.min.time())
    end = start + timedelta(days=1)
    tasks = (db.query(DdlTask)
             .filter(DdlTask.user_id == user_id, DdlTask.status == "pending",
                     DdlTask.due_at >= start, DdlTask.due_at < end).all())
    return sorted(tasks, key=lambda t: (PRIORITY_WEIGHT.get(t.priority, 1), t.due_at or datetime.max))


def categories(db: Session, user_id: int) -> list[str]:
    rows = (db.query(DdlTask.category).filter(DdlTask.user_id == user_id)
            .distinct().all())
    return [r[0] for r in rows if r[0]]
