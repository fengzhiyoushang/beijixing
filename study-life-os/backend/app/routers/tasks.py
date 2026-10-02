"""DDL 任务：全生命周期 CRUD / 完成 / 倒计时过滤 / 统计分析。"""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import get_db
from app.core.deps import get_current_user
from app.schemas import TaskIn, TaskPatchIn

router = APIRouter(prefix="/tasks", tags=["DDL任务"])


def _get_task(db: Session, uid: int, task_id: int) -> m.Task:
    task = db.get(m.Task, task_id)
    if not task or task.user_id != uid:
        raise HTTPException(404, "任务不存在")
    return task


@router.get("")
def list_tasks(
    status: str | None = Query(None),
    category: str | None = Query(None),
    search: str | None = Query(None),
    within_days: int | None = Query(None, ge=1, le=90),
    db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
):
    q = db.query(m.Task).filter(m.Task.user_id == user.id)
    if status:
        q = q.filter(m.Task.status == status)
    if category:
        q = q.filter(m.Task.category == category)
    if search:
        q = q.filter(m.Task.title.contains(search))
    if within_days:
        horizon = datetime.now() + timedelta(days=within_days)
        q = q.filter(m.Task.due_at.isnot(None), m.Task.due_at <= horizon)
    tasks = q.order_by(m.Task.status, m.Task.due_at).all()
    now = datetime.now()
    return [t.to_dict(now) for t in tasks]


@router.get("/stats")
def stats(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    from app.services.dashboard import task_stats
    return task_stats(db, user.id)


@router.get("/upcoming")
def upcoming(
    days: int = Query(7, ge=1, le=90),
    db: Session = Depends(get_db),
    user: m.User = Depends(get_current_user),
):
    now = datetime.now()
    horizon = now + timedelta(days=days)
    tasks = (
        db.query(m.Task)
        .filter(m.Task.user_id == user.id, m.Task.status == "pending",
                m.Task.due_at.isnot(None), m.Task.due_at <= horizon)
        .order_by(m.Task.due_at)
        .all()
    )
    return [t.to_dict(now) for t in tasks]


@router.post("", status_code=201)
def create_task(body: TaskIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    task = m.Task(
        user_id=user.id, title=body.title, description=body.description,
        category=body.category, priority=body.priority, due_at=body.due_at,
        progress=body.progress, tags=body.tags,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.put("/{task_id}")
def update_task(task_id: int, body: TaskPatchIn, db: Session = Depends(get_db),
                user: m.User = Depends(get_current_user)):
    task = _get_task(db, user.id, task_id)
    data = body.model_dump(exclude_unset=True)
    if "status" in data and data["status"] == "done" and task.status != "done":
        task.done_at = datetime.now()
        data.setdefault("progress", 100)
    if "status" in data and data["status"] == "pending":
        task.done_at = None
    for k, v in data.items():
        setattr(task, k, v)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.post("/{task_id}/complete")
def complete_task(task_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    task = _get_task(db, user.id, task_id)
    task.status = "done"
    task.done_at = datetime.now()
    task.progress = 100
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.delete("/{task_id}")
def delete_task(task_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    task = _get_task(db, user.id, task_id)
    db.delete(task)
    db.commit()
    return {"deleted": task_id}
