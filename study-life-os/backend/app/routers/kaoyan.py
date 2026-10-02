"""考研目标分析与学习规划：差距分析 → 阶段生成 → 每日拆解 → 复盘。

设计原则：数值计算全部走规则引擎（防幻觉），DeepSeek 只负责基于数值生成建议文本；
无 API Key 时建议文本退化为规则模板，流程不中断。
"""
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models as m
from app.core.database import get_db
from app.core.deps import get_current_user
from app.services import dashboard as dash_svc, deepseek
from app.schemas import (GoalIn, PhaseIn, PlanGenerateIn, PlanTaskIn,
                         PlanTaskPatchIn, ReviewIn)

router = APIRouter(prefix="/kaoyan", tags=["考研规划"])


def _active_goal(db: Session, uid: int) -> m.KaoyanGoal | None:
    return (db.query(m.KaoyanGoal)
            .filter(m.KaoyanGoal.user_id == uid, m.KaoyanGoal.status == "active")
            .order_by(m.KaoyanGoal.id.desc()).first())


def _require_goal(db: Session, uid: int) -> m.KaoyanGoal:
    goal = _active_goal(db, uid)
    if goal is None:
        raise HTTPException(400, "请先在「考研规划」模块录入目标院校与分数线")
    return goal


def _subject_gaps(goal: m.KaoyanGoal) -> list[dict]:
    subjects = (goal.detail or {}).get("subjects", {})
    gaps = []
    for name, s in subjects.items():
        target, current, mx = s.get("target", 0), s.get("current", 0), s.get("max", 100) or 100
        gaps.append({
            "subject": name, "target": target, "current": current, "max": mx,
            "gap": round(target - current, 1),
            "gap_ratio": round((target - current) / mx, 3) if mx else 0,
            "reach_rate": round(current / target, 3) if target else 0,
        })
    gaps.sort(key=lambda x: -x["gap"])
    return gaps


@router.get("/goal")
def get_goal(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _active_goal(db, user.id)
    return goal.to_dict() if goal else None


@router.put("/goal")
def upsert_goal(body: GoalIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _active_goal(db, user.id)
    if goal is None:
        goal = m.KaoyanGoal(user_id=user.id)
        db.add(goal)
    for k, v in body.model_dump().items():
        setattr(goal, k, v)
    if body.detail and isinstance(body.detail, dict) and body.detail.get("subjects"):
        subs = body.detail["subjects"]
        # 未显式传入总分时，随科目分数自动重算，避免遗留旧值
        if body.total_target is None:
            goal.total_target = sum(s.get("target", 0) for s in subs.values())
        if body.total_current is None:
            goal.total_current = sum(s.get("current", 0) for s in subs.values())
    db.commit()
    db.refresh(goal)
    return goal.to_dict()


@router.delete("/goal")
def delete_goal(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _active_goal(db, user.id)
    if goal is None:
        raise HTTPException(404, "暂无目标")
    db.delete(goal)
    db.commit()
    return {"deleted": True}


@router.get("/gap-analysis")
@router.post("/gap-analysis")
async def gap_analysis(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _require_goal(db, user.id)
    gaps = _subject_gaps(goal)
    days_left = (goal.exam_date - date.today()).days if goal.exam_date else None
    weeks_left = (days_left // 7) if days_left and days_left > 0 else None
    numeric = {
        "subjects": gaps,
        "total_target": goal.total_target,
        "total_current": goal.total_current,
        "total_gap": round(goal.total_target - goal.total_current, 1),
        "days_left": days_left,
        "weeks_left": weeks_left,
        "weekly_gap": round((goal.total_target - goal.total_current) / weeks_left, 2) if weeks_left else None,
    }
    hint_lines = []
    if days_left is not None and days_left < 0:
        hint_lines.append("目标考试日期已过，请更新考试日期或归档目标。")
    for g in gaps[:3]:
        hint_lines.append(f"{g['subject']}：距目标 {g['gap']} 分（达成率 {int(g['reach_rate']*100)}%）")

    ai_report = None
    if deepseek.is_configured():
        prompt = (
            "你是考研规划分析师。基于以下客观数据，输出不超过 400 字的 Markdown 诊断报告，"
            "包含：总分差距判断、时间压力、各科优先级排序与一句风险提示；不要编造数据之外的数字。\n\n"
            f"目标：{goal.target_school} {goal.target_major or ''}｜总分目标 {goal.total_target}"
            f"｜当前预估 {goal.total_current}｜剩余 {days_left} 天\n"
            f"各科：{gaps}"
        )
        try:
            msg = await deepseek.chat([
                {"role": "system", "content": "你是严谨的考研规划分析师，回答精炼。"},
                {"role": "user", "content": prompt},
            ], temperature=0.4)
            ai_report = msg.get("content")
        except Exception as exc:
            ai_report = f"（AI 分析暂不可用：{exc}）"
    return {"numeric": numeric, "rule_summary": "\n".join(hint_lines),
            "ai_report": ai_report, "ai_available": deepseek.is_configured()}


@router.post("/plan/generate")
async def generate_plan(body: PlanGenerateIn, db: Session = Depends(get_db),
                        user: m.User = Depends(get_current_user)):
    goal = _require_goal(db, user.id)
    exam = goal.exam_date or date.today() + timedelta(days=180)
    total_days = max((exam - date.today()).days, 14)

    # 规则引擎先定阶段框架（时间窗与科目优先级不依赖模型）
    b1 = int(total_days * 0.45)
    b2 = int(total_days * 0.8)
    today = date.today()
    gaps = _subject_gaps(goal)
    weak = "、".join(g["subject"] for g in gaps[:2]) or "全科"
    phase_defs = [
        ("基础夯实期", today, today + timedelta(days=b1),
         f"补齐短板（重点：{weak}）；建立全科知识框架，完成基础题库一轮"),
        ("强化提升期", today + timedelta(days=b1 + 1), today + timedelta(days=b2),
         "真题分科专项训练，整理错题本；主攻分值最大的题型模块"),
        ("冲刺模考期", today + timedelta(days=b2 + 1), exam,
         "全真模考与答题卡节奏训练；政治大题与英语作文背诵冲刺"),
    ]
    db.query(m.PlanPhase).filter(m.PlanPhase.goal_id == goal.id).delete(synchronize_session=False)
    db.commit()
    phases = []
    for i, (name, s, e, obj) in enumerate(phase_defs):
        p = m.PlanPhase(goal_id=goal.id, name=name, start_date=s, end_date=e,
                        objective=obj, sort_no=i + 1,
                        status="active" if i == 0 else "pending")
        db.add(p)
        db.flush()
        phases.append(p)

    created_daily = 0
    if body.auto_daily and phases:
        first = phases[0]
        pool = [g for g in gaps if g["gap"] > 0][:4] or [
            {"subject": g["subject"], "gap": 50, "max": 100} for g in _subject_gaps(goal)[:4]
        ]
        for d in range(body.daily_days):
            day = today + timedelta(days=d)
            for item in pool:
                minutes = max(30, min(150, int(item["gap"] / max(item["max"], 1) * 100) // 10 * 10))
                db.add(m.PlanTask(
                    phase_id=first.id, date=day,
                    title=f"{item['subject']}专项 {minutes} 分钟（缺口 {item['gap']} 分）",
                    subject=item["subject"], planned_minutes=minutes,
                ))
                created_daily += 1
    db.commit()
    for p in phases:
        db.refresh(p)
    return {"phases": [p.to_dict() for p in phases], "daily_tasks_created": created_daily,
            "tip": "阶段框架由规则引擎基于剩余天数与各科缺口生成；可随时在页面上手工调整。"}


@router.get("/phases")
def list_phases(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _active_goal(db, user.id)
    return [p.to_dict() for p in (goal.phases if goal else [])]


@router.post("/phases", status_code=201)
def create_phase(body: PhaseIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _require_goal(db, user.id)
    phase = m.PlanPhase(goal_id=goal.id, **body.model_dump())
    db.add(phase)
    db.commit()
    db.refresh(phase)
    return phase.to_dict()


@router.patch("/phases/{phase_id}")
def patch_phase(phase_id: int, body: PhaseIn, db: Session = Depends(get_db),
                user: m.User = Depends(get_current_user)):
    phase = db.get(m.PlanPhase, phase_id)
    if not phase or phase.goal.user_id != user.id:
        raise HTTPException(404, "阶段不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(phase, k, v)
    db.commit()
    db.refresh(phase)
    return phase.to_dict()


@router.delete("/phases/{phase_id}")
def delete_phase(phase_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    phase = db.get(m.PlanPhase, phase_id)
    if not phase or phase.goal.user_id != user.id:
        raise HTTPException(404, "阶段不存在")
    db.delete(phase)
    db.commit()
    return {"deleted": phase_id}


@router.get("/daily-tasks")
def daily_tasks(day: str | None = Query(None, alias="date"),
                db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    d = date.fromisoformat(day) if day else date.today()
    goal = _active_goal(db, user.id)
    if not goal:
        return {"date": d.isoformat(), "tasks": []}
    tasks = [t for p in goal.phases for t in p.tasks if t.date == d]
    phase_name = {p.id: p.name for p in goal.phases}
    return {"date": d.isoformat(),
            "tasks": [{**t.to_dict(), "phase_name": phase_name.get(t.phase_id)} for t in tasks]}


@router.post("/daily-tasks", status_code=201)
def add_daily_task(body: PlanTaskIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _require_goal(db, user.id)
    active = next((p for p in goal.phases if p.status == "active"), goal.phases[0] if goal.phases else None)
    if active is None:
        raise HTTPException(400, "请先生成阶段规划")
    task = m.PlanTask(phase_id=active.id, **body.model_dump())
    db.add(task)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.patch("/tasks/{task_id}")
def patch_plan_task(task_id: int, body: PlanTaskPatchIn, db: Session = Depends(get_db),
                    user: m.User = Depends(get_current_user)):
    task = db.get(m.PlanTask, task_id)
    if not task or task.phase.goal.user_id != user.id:
        raise HTTPException(404, "任务不存在")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(task, k, v)
    db.commit()
    db.refresh(task)
    return task.to_dict()


@router.delete("/tasks/{task_id}")
def delete_plan_task(task_id: int, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    task = db.get(m.PlanTask, task_id)
    if not task or task.phase.goal.user_id != user.id:
        raise HTTPException(404, "任务不存在")
    db.delete(task)
    db.commit()
    return {"deleted": task_id}


@router.get("/progress")
def progress(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    overview = dash_svc.kaoyan_overview(db, user.id)
    if not overview:
        return None
    goal = _active_goal(db, user.id)
    today = date.today()
    recent = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        tasks = [t for p in goal.phases for t in p.tasks if t.date == d]
        if tasks:
            recent.append({"date": d.isoformat(), "total": len(tasks),
                           "done": sum(1 for t in tasks if t.done)})
    return {**overview, "daily_trend14": recent}


@router.post("/review")
async def review(body: ReviewIn, db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    goal = _require_goal(db, user.id)
    today = date.today()
    since = today - timedelta(days=body.days - 1)
    tasks = [t for p in goal.phases for t in p.tasks if since <= t.date <= today]
    done = [t for t in tasks if t.done]
    notes = [t.review_note for t in done if t.review_note]
    checks = (db.query(m.CheckinRecord)
              .filter(m.CheckinRecord.user_id == user.id, m.CheckinRecord.date >= since).all())
    focus_min = sum(c.minutes for c in checks)
    numeric = {
        "days": body.days,
        "planned": len(tasks), "done": len(done),
        "done_rate": round(len(done) / len(tasks), 3) if tasks else None,
        "planned_minutes": sum(t.planned_minutes for t in tasks),
        "done_minutes": sum(t.done_minutes or 0 for t in done),
        "checkin_minutes": focus_min,
    }
    rule_report = (
        f"近 {body.days} 天：拆解任务 {numeric['planned']} 项，完成 {numeric['done']} 项"
        f"（完成率 {int((numeric['done_rate'] or 0) * 100)}%）；"
        f"计划专注 {numeric['planned_minutes']} 分钟，实际打卡 {focus_min} 分钟。"
    )
    ai_text = None
    if deepseek.is_configured():
        prompt = (
            f"用户考研周复盘数据：{numeric}；复盘笔记：{notes or '无'}；"
            f"目标：{goal.target_school}（剩余 {numeric['days']} 天窗口）。"
            "请输出 200 字以内 Markdown 复盘点评：亮点、风险、下周一条调整建议。"
        )
        try:
            msg = await deepseek.chat([
                {"role": "system", "content": "你是学习教练，基于数据复盘，不编造。"},
                {"role": "user", "content": prompt}], temperature=0.4)
            ai_text = msg.get("content")
        except Exception:
            ai_text = None
    goal.detail = {**(goal.detail or {}),
                   "last_review": {"date": today.isoformat(), "text": (ai_text or rule_report)[:2000]}}
    db.commit()
    return {"numeric": numeric, "rule_report": rule_report, "ai_report": ai_text,
            "notes": notes}
