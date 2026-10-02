"""DDL 任务路由：CRUD、子任务、分类筛选、统计、临近提醒。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.task import SubTaskIn, SubTaskUpdate, TaskIn, TaskUpdate
from app.services import task_service

router = APIRouter(prefix="/tasks", tags=["③ DDL 任务"])


# ─────────── 统计与筛选（置于 /{task_id} 之前） ───────────
@router.get("/stats", summary="任务统计（数量/完成率/分类/优先级/趋势）")
def stats(days: int = Query(default=7, ge=1, le=90), db: Session = Depends(get_db),
          user: User = Depends(get_current_user)) -> dict:
    return task_service.stats(db, user.id, days=days)


@router.get("/upcoming", summary="临近截止任务")
def upcoming(within_days: int = Query(default=7, ge=1, le=90),
             limit: int = Query(default=20, ge=1, le=100),
             db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    tasks = task_service.upcoming(db, user.id, within_days=within_days, limit=limit)
    return {"total": len(tasks), "items": [t.to_dict() for t in tasks]}


@router.get("/today", summary="今日到期任务（按优先级排序）")
def today(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    tasks = task_service.today_due(db, user.id)
    return {"total": len(tasks), "items": [t.to_dict() for t in tasks]}


@router.get("/categories", summary="任务分类列表")
def categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"items": task_service.categories(db, user.id)}


# ─────────── CRUD ───────────
@router.get("", summary="任务列表（支持状态/分类/优先级/关键词/时间范围筛选）")
def list_tasks(status: str | None = Query(default=None),
               category: str | None = Query(default=None),
               priority: str | None = Query(default=None),
               keyword: str | None = Query(default=None),
               course_id: int | None = Query(default=None),
               order: str = Query(default="due", pattern="^(due|created|priority)$"),
               db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    tasks = task_service.list_tasks(db, user.id, status=status, category=category,
                                    priority=priority, keyword=keyword, course_id=course_id,
                                    order=order)
    return {"total": len(tasks), "items": [t.to_dict() for t in tasks]}


@router.post("", summary="新建任务（可同时带子任务）")
def create_task(body: TaskIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    task = task_service.create_task(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return task.to_dict()


@router.get("/{task_id}", summary="任务详情")
def get_task(task_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    return task_service.get_task(db, user.id, task_id).to_dict()


@router.put("/{task_id}", summary="更新任务")
def update_task(task_id: int, body: TaskUpdate, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    task = task_service.update_task(db, user.id, task_id, body)
    dashboard_service.invalidate(user.id)
    return task.to_dict()


@router.delete("/{task_id}", summary="删除任务")
def delete_task(task_id: int, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    task_service.delete_task(db, user.id, task_id)
    dashboard_service.invalidate(user.id)
    return {"deleted": True}


@router.post("/{task_id}/complete", summary="标记完成")
def complete(task_id: int, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    task = task_service.complete_task(db, user.id, task_id, done=True)
    dashboard_service.invalidate(user.id)
    return task.to_dict()


@router.post("/{task_id}/uncomplete", summary="取消完成")
def uncomplete(task_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    from app.services import dashboard_service

    task = task_service.complete_task(db, user.id, task_id, done=False)
    dashboard_service.invalidate(user.id)
    return task.to_dict()


# ─────────── 子任务 ───────────
@router.post("/{task_id}/subtasks", summary="新增子任务")
def add_subtask(task_id: int, body: SubTaskIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    return task_service.add_subtask(db, user.id, task_id, body).to_dict()


@router.put("/subtasks/{subtask_id}", summary="更新子任务（勾选/改名）")
def update_subtask(subtask_id: int, body: SubTaskUpdate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    return task_service.update_subtask(db, user.id, subtask_id, body).to_dict()


@router.delete("/subtasks/{subtask_id}", summary="删除子任务")
def delete_subtask(subtask_id: int, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    task_service.delete_subtask(db, user.id, subtask_id)
    return {"deleted": True}
