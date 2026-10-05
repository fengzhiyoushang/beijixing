"""考研规划路由：目标管理、成绩录入、差距分析、计划生成。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import NotFoundError
from app.models.kaoyan import KaoyanPlanPhase, KaoyanPlanTask
from app.models.user import User
from app.schemas.kaoyan import (KaoyanTargetIn, KaoyanTargetUpdate, PhaseIn, PhaseUpdate,
                                PlanGenerateIn, PlanTaskIn, PlanTaskUpdate, ScoreIn)
from app.services import dashboard_service, kaoyan_intel_service, kaoyan_service

router = APIRouter(prefix="/kaoyan", tags=["⑦ 考研规划"])


# ─────────── 目标 ───────────
@router.get("/target", summary="获取当前考研目标")
def get_target(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    target = kaoyan_service.get_active_target(db, user.id)
    return target.to_dict() if target else {}


@router.put("/target", summary="新建/更新考研目标（各科分数线 + 当前成绩）")
def upsert_target(body: KaoyanTargetIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    target = kaoyan_service.upsert_target(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return target.to_dict()


@router.patch("/target", summary="部分更新考研目标")
def patch_target(body: KaoyanTargetUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    target = kaoyan_service.upsert_target(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return target.to_dict()


@router.delete("/target/{target_id}", summary="删除考研目标")
def delete_target(target_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    kaoyan_service.delete_target(db, user.id, target_id)
    dashboard_service.invalidate(user.id)
    return {"deleted": True}


# ─────────── 差距分析与成绩 ───────────
@router.get("/gap-analysis", summary="差距分析（各科差距、提分优先级、周均目标）")
def gap_analysis(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    target = kaoyan_service.require_target(db, user.id)
    return kaoyan_service.gap_analysis(db, target)


@router.post("/scores", summary="成绩录入（更新科目当前分，可同步写学习记录）")
def record_score(body: ScoreIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    result = kaoyan_service.record_score(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return result


@router.get("/progress", summary="考研进度（阶段/每日任务/科目达成）")
def progress(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return kaoyan_service.progress(db, user.id)


# ─────────── 考研情报（聚焦爬虫：分数线 / 复试 / 就业） ───────────
@router.get("/intel", summary="目标院校专业历年分数线与就业情报（带缓存）")
def get_intel(refresh: bool = Query(default=False), db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> dict:
    return kaoyan_intel_service.get_for_user(db, user.id, force=refresh)


# ─────────── 计划 ───────────
@router.post("/plan/generate", summary="生成学习计划（DeepSeek 优先，失败回退规则引擎）")
async def generate_plan(body: PlanGenerateIn, db: Session = Depends(get_db),
                        user: User = Depends(get_current_user)) -> dict:
    result = await kaoyan_service.generate_plan(db, user.id, body)
    dashboard_service.invalidate(user.id)
    return result


@router.get("/plans", summary="阶段计划列表（含每日任务）")
def list_plans(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    target = kaoyan_service.require_target(db, user.id)
    return {"target_id": target.id,
            "phases": [p.to_dict() for p in target.phases]}


@router.post("/plans/phases", summary="手动新增阶段")
def create_phase(body: PhaseIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    target = kaoyan_service.require_target(db, user.id)
    phase = KaoyanPlanPhase(target_id=target.id, name=body.name, start_date=body.start_date,
                            end_date=body.end_date, focus=body.focus, subjects=body.subjects,
                            progress=body.progress, sort_order=body.sort_order)
    db.add(phase)
    db.commit()
    db.refresh(phase)
    return phase.to_dict()


@router.put("/plans/phases/{phase_id}", summary="更新阶段（进度/时间范围）")
def update_phase(phase_id: int, body: PhaseUpdate, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    phase = db.get(KaoyanPlanPhase, phase_id)
    if not phase or not phase.target or phase.target.user_id != user.id:
        raise NotFoundError("阶段不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(phase, key, value)
    db.commit()
    db.refresh(phase)
    return phase.to_dict()


@router.delete("/plans/phases/{phase_id}", summary="删除阶段")
def delete_phase(phase_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    phase = db.get(KaoyanPlanPhase, phase_id)
    if not phase or not phase.target or phase.target.user_id != user.id:
        raise NotFoundError("阶段不存在")
    db.delete(phase)
    db.commit()
    return {"deleted": True}


# ─────────── 每日任务 ───────────
@router.get("/plan/tasks", summary="每日任务列表")
def list_plan_tasks(plan_date: str | None = Query(default=None), db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    target = kaoyan_service.get_active_target(db, user.id)
    if not target:
        return {"items": []}
    tasks = [t for p in target.phases for t in p.tasks]
    if plan_date:
        tasks = [t for t in tasks if t.plan_date and t.plan_date.isoformat() == plan_date]
    return {"total": len(tasks), "items": [t.to_dict() for t in tasks]}


@router.post("/plan/tasks", summary="新增每日任务")
def create_plan_task(body: PlanTaskIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    phase = db.get(KaoyanPlanPhase, body.phase_id)
    if not phase or not phase.target or phase.target.user_id != user.id:
        raise NotFoundError("阶段不存在")
    task = KaoyanPlanTask(phase_id=phase.id, title=body.title, subject=body.subject,
                          minutes=body.minutes, plan_date=body.plan_date)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.put("/plan/tasks/{task_id}", summary="更新每日任务（勾选完成）")
def update_plan_task(task_id: int, body: PlanTaskUpdate, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    task = db.get(KaoyanPlanTask, task_id)
    if not task or not task.phase or not task.phase.target or task.phase.target.user_id != user.id:
        raise NotFoundError("计划任务不存在")
    for key, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(task, key, value)
    # 阶段进度 = 已完成任务占比
    siblings = task.phase.tasks
    if siblings:
        task.phase.progress = round(sum(1 for t in siblings if t.is_done) / len(siblings) * 100)
    db.commit()
    db.refresh(task)
    dashboard_service.invalidate(user.id)
    return task.to_dict()


@router.delete("/plan/tasks/{task_id}", summary="删除每日任务")
def delete_plan_task(task_id: int, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    task = db.get(KaoyanPlanTask, task_id)
    if not task or not task.phase or not task.phase.target or task.phase.target.user_id != user.id:
        raise NotFoundError("计划任务不存在")
    db.delete(task)
    db.commit()
    return {"deleted": True}
