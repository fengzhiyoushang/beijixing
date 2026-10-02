"""考研服务：目标管理、差距分析、成绩录入、计划生成（AI + 规则回退）。"""
from __future__ import annotations

import json
import logging
import re
from datetime import date, timedelta

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.ai import prompts
from app.ai.deepseek import deepseek
from app.core.exceptions import AppError, NotFoundError
from app.models.kaoyan import KaoyanPlanPhase, KaoyanPlanTask, KaoyanTarget
from app.models.study import StudyRecord

logger = logging.getLogger("polaris.kaoyan")


# ─────────── 目标管理 ───────────
def get_active_target(db: Session, user_id: int) -> KaoyanTarget | None:
    return (db.query(KaoyanTarget)
            .filter(KaoyanTarget.user_id == user_id, KaoyanTarget.status == "active")
            .order_by(KaoyanTarget.id.desc()).first())


def require_target(db: Session, user_id: int) -> KaoyanTarget:
    target = get_active_target(db, user_id)
    if not target:
        raise AppError("请先录入考研目标院校与分数线", code="no_target", status_code=404)
    return target


def upsert_target(db: Session, user_id: int, payload) -> KaoyanTarget:
    target = get_active_target(db, user_id)
    if target is None:
        target = KaoyanTarget(user_id=user_id)
        db.add(target)

    data = payload.model_dump(exclude_unset=True)
    subjects = data.pop("subject_scores", None)
    for key, value in data.items():
        if value is not None:
            setattr(target, key, value)

    if subjects is not None:
        normalized = []
        for item in subjects:
            item = item if isinstance(item, dict) else item.model_dump()
            normalized.append({
                "subject": item["subject"],
                "target": float(item.get("target") or 0),
                "current": float(item.get("current") or 0),
                "max": float(item.get("max") or 100),
                "line": float(item["line"]) if item.get("line") is not None else None,
                "note": item.get("note"),
            })
        target.subject_scores = normalized
        if data.get("total_target") is None:
            target.total_target = sum(x["target"] for x in normalized)
        if data.get("total_current") is None:
            target.total_current = sum(x["current"] for x in normalized)

    db.commit()
    db.refresh(target)
    target.gap_analysis = gap_analysis(db, target)
    db.commit()
    db.refresh(target)
    return target


def delete_target(db: Session, user_id: int, target_id: int) -> None:
    target = db.get(KaoyanTarget, target_id)
    if not target or target.user_id != user_id:
        raise NotFoundError("目标不存在")
    db.delete(target)
    db.commit()


# ─────────── 差距分析 ───────────
def gap_analysis(db: Session, target: KaoyanTarget) -> dict:
    subjects = target.subject_scores or []
    gaps = []
    for item in subjects:
        cur, tgt = float(item.get("current") or 0), float(item.get("target") or 0)
        mx = float(item.get("max") or 100)
        gap = round(tgt - cur, 1)
        gaps.append({
            "subject": item["subject"],
            "current": cur,
            "target": tgt,
            "max": mx,
            "line": item.get("line"),
            "gap": gap,
            "gap_ratio": round(gap / mx, 4) if mx else 0,
            "reach_rate": round(cur / tgt, 4) if tgt else 0,
            # 提分性价比：单位分数对应的难度（gap 越大越难，但仍按 gap 排序给出优先级）
            "priority_score": round(gap / mx * 100, 2) if mx else 0,
        })
    gaps.sort(key=lambda x: -x["gap"])

    days_left = (target.exam_date - date.today()).days if target.exam_date else None
    weeks_left = max(1, days_left // 7) if days_left and days_left > 0 else None
    total_gap = round((target.total_target or 0) - (target.total_current or 0), 1)

    focus = [g["subject"] for g in gaps[:2]]
    suggestion = (
        f"距初试 {days_left} 天（约 {weeks_left} 周），总分差 {total_gap} 分，"
        f"平均每周需提升 {round(total_gap / weeks_left, 1) if weeks_left else 0} 分。"
        f"优先补强：{'、'.join(focus) if focus else '先完善各科目标设定'}。"
    )

    return {
        "school": target.school,
        "major": target.major,
        "exam_date": target.exam_date.isoformat() if target.exam_date else None,
        "days_left": days_left,
        "weeks_left": weeks_left,
        "total_target": target.total_target,
        "total_current": target.total_current,
        "total_gap": total_gap,
        "progress": round((target.total_current or 0) / target.total_target * 100, 1)
        if target.total_target else 0,
        "weekly_gap": round(total_gap / weeks_left, 2) if weeks_left else None,
        "subjects": gaps,
        "focus_subjects": focus,
        "suggestion": suggestion,
    }


def record_score(db: Session, user_id: int, payload) -> dict:
    """成绩录入：更新目标科目当前分，可同时写学习记录。"""
    target = require_target(db, user_id)
    subjects = target.subject_scores or []
    updated = False
    for item in subjects:
        if item["subject"] == payload.subject:
            item["current"] = float(payload.current)
            updated = True
            break
    if not updated:
        subjects.append({"subject": payload.subject, "target": payload.current,
                         "current": float(payload.current), "max": 100, "line": None, "note": "新增科目"})
    target.subject_scores = subjects
    target.total_current = sum(float(x.get("current") or 0) for x in subjects)
    target.gap_analysis = gap_analysis(db, target)
    flag_modified(target, "subject_scores")
    db.commit()

    if payload.add_study_record:
        db.add(StudyRecord(
            user_id=user_id, date=payload.date or date.today(), subject=payload.subject,
            minutes=payload.minutes, content=f"成绩录入：{payload.mock_name or '模考'} {payload.current} 分",
            mock_name=payload.mock_name, mock_score=payload.current,
            mock_full_score=next((x.get("max") for x in subjects if x["subject"] == payload.subject), 100),
        ))
        db.commit()

    db.refresh(target)
    return {"target": target.to_dict(with_phases=False), "gap_analysis": target.gap_analysis}


# ─────────── 计划生成 ───────────
def _phases_by_ratio(total_weeks: int) -> list[tuple[str, int, str]]:
    """规则引擎：按 45% / 35% / 20% 拆分基础、强化、冲刺。"""
    base = max(1, round(total_weeks * 0.45))
    strengthen = max(1, round(total_weeks * 0.35))
    sprint = max(1, total_weeks - base - strengthen)
    return [
        ("基础阶段", base, "教材通读 + 基础题全覆盖，建立知识框架与笔记体系"),
        ("强化阶段", strengthen, "专题突破 + 真题一轮，错题归档进入知识库做 RAG 复盘"),
        ("冲刺阶段", sprint, "模拟卷限时训练 + 查漏补缺 + 政治与英语背诵冲刺"),
    ]


RULE_DAILY_TEMPLATE = {
    "数学": ["高数专题强化 20 题", "线代/概率章节练习", "真题限时训练 + 错题订正"],
    "英语": ["阅读理解 2 篇精析", "长难句拆解 5 句", "核心词汇 60 个 + 作文模板"],
    "政治": ["马原/毛中特 强化课", "选择题 30 题", "时政要点整理"],
    "408": ["数据结构算法题 3 道", "操作系统大题 1 道", "计算机网络章节精讲", "组成原理计算题"],
}


def _rule_plan(target: KaoyanTarget, payload) -> dict:
    """无 AI 或 AI 失败时的规则计划。"""
    subjects = payload.subjects or [s["subject"] for s in (target.subject_scores or [])] or ["数学", "英语", "政治", "408"]
    total_weeks = payload.total_weeks
    phases_raw = _phases_by_ratio(total_weeks)

    phases = []
    for name, weeks, focus in phases_raw:
        phases.append({"name": name, "weeks": weeks, "focus": focus,
                       "subjects": subjects, "progress": 0})

    # 每日任务：按 weakest-first 轮转，minutes 按 gap 比例分配
    gaps = {s["subject"]: float(s.get("gap") or 0) for s in (target.subject_scores or [])}
    remaining = payload.daily_minutes
    daily_tasks = []
    per_subject_budget: dict[str, int] = {}
    total_gap = sum(gaps.values()) or len(subjects)
    for subject in subjects:
        weight = (gaps.get(subject, 0) or 1) / total_gap
        minutes = max(30, int(payload.daily_minutes * max(0.12, weight)))
        per_subject_budget[subject] = minutes
        remaining -= minutes
    # 若超支，等比例压缩
    if remaining < 0:
        factor = payload.daily_minutes / sum(per_subject_budget.values())
        per_subject_budget = {k: max(20, int(v * factor)) for k, v in per_subject_budget.items()}

    for subject, minutes in per_subject_budget.items():
        templates = RULE_DAILY_TEMPLATE.get(subject, [f"{subject} 专项训练"])
        for title in templates[:2]:
            daily_tasks.append({"subject": subject, "title": title, "minutes": max(20, minutes // 2)})

    return {
        "phases": phases,
        "daily_tasks": daily_tasks[:8],
        "advice": "规则引擎生成：数学与 408 提分空间最大，优先保证每日真题训练量；"
                  "英语重阅读与词汇积累，政治放在冲刺阶段集中突破。",
        "source": "rule",
    }


async def _ai_plan(target: KaoyanTarget, payload) -> dict | None:
    if not (payload.use_ai and deepseek.is_configured):
        return None
    subjects_desc = "；".join(
        f"{s['subject']} {s.get('current', 0)}/{s.get('target', 0)}（满分 {s.get('max', 100)}）"
        for s in (target.subject_scores or [])
    ) or "未录入"
    prompt = prompts.KAOYAN_PLAN_PROMPT.format(
        school=target.school, major=target.major, degree_type=target.degree_type,
        exam_date=target.exam_date.isoformat() if target.exam_date else "未定",
        days_left=(target.exam_date - date.today()).days if target.exam_date else "未知",
        total_weeks=payload.total_weeks, total_target=target.total_target,
        total_current=target.total_current, subjects=subjects_desc,
        daily_minutes=payload.daily_minutes,
    )
    try:
        message = await deepseek.chat(
            [{"role": "system", "content": "你是考研规划专家，输出严格 JSON。"},
             {"role": "user", "content": prompt}],
            temperature=0.4,
        )
        data = _parse_json(message.get("content") or "")
        if not data or not data.get("phases"):
            return None
        data["source"] = "ai"
        return data
    except Exception as exc:                     # pragma: no cover
        logger.warning("AI 计划生成失败，回退规则引擎：%s", exc)
        return None


def _parse_json(text: str) -> dict | None:
    cleaned = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


async def generate_plan(db: Session, user_id: int, payload) -> dict:
    """生成阶段计划 + 每日任务（AI 优先，规则回退）。"""
    target = require_target(db, user_id)
    plan = await _ai_plan(target, payload) or _rule_plan(target, payload)

    if payload.replace_existing:
        db.query(KaoyanPlanPhase).filter(KaoyanPlanPhase.target_id == target.id).delete()
        db.commit()

    total_weeks = payload.total_weeks
    start = date.today()
    weeks_left = total_weeks
    created_phases = []

    for i, phase in enumerate(plan["phases"]):
        weeks = int(phase.get("weeks") or max(1, weeks_left // max(1, len(plan["phases"]) - i)))
        weeks = max(1, min(weeks, weeks_left))
        phase_start = start
        phase_end = start + timedelta(weeks=weeks) - timedelta(days=1)
        row = KaoyanPlanPhase(
            target_id=target.id,
            name=phase.get("name") or f"阶段{i + 1}",
            start_date=phase_start,
            end_date=phase_end,
            focus=phase.get("focus"),
            subjects=phase.get("subjects") or [],
            progress=int(phase.get("progress") or 0),
            sort_order=i,
            source=plan.get("source", "rule"),
        )
        db.add(row)
        db.flush()
        created_phases.append(row)
        start = phase_end + timedelta(days=1)
        weeks_left -= weeks

    # 每日任务挂在第一个阶段下
    created_tasks = []
    if payload.include_daily_tasks and created_phases:
        phase = created_phases[0]
        for j, task in enumerate(plan.get("daily_tasks") or []):
            row = KaoyanPlanTask(
                phase_id=phase.id,
                title=task.get("title") or f"任务{j + 1}",
                subject=task.get("subject") or "综合",
                minutes=int(task.get("minutes") or 60),
                plan_date=date.today() + timedelta(days=j // 3),
            )
            db.add(row)
            created_tasks.append(row)

    db.commit()
    db.refresh(target)
    return {
        "target": target.to_dict(with_phases=True),
        "source": plan.get("source", "rule"),
        "advice": plan.get("advice"),
        "phases": len(created_phases),
        "daily_tasks": len(created_tasks),
    }


def progress(db: Session, user_id: int) -> dict:
    """考研进度：阶段完成度、每日任务完成率、科目达成率。"""
    target = get_active_target(db, user_id)
    if not target:
        return {"has_target": False}
    phases = target.phases
    tasks = [t for p in phases for t in p.tasks]
    done_tasks = sum(1 for t in tasks if t.is_done)
    gap = gap_analysis(db, target)
    return {
        "has_target": True,
        "school": target.school,
        "major": target.major,
        "days_left": gap["days_left"],
        "overall_progress": gap["progress"],
        "phase_progress": round(sum(p.progress for p in phases) / len(phases), 1) if phases else 0,
        "phases": [{"name": p.name, "progress": p.progress, "range":
                    f"{p.start_date} ~ {p.end_date}" if p.start_date else None} for p in phases],
        "daily_task_rate": round(done_tasks / len(tasks), 4) if tasks else 0,
        "daily_tasks": [t.to_dict() for t in tasks[:12]],
        "total_gap": gap["total_gap"],
        "weekly_gap": gap["weekly_gap"],
        "focus_subjects": gap["focus_subjects"],
    }
