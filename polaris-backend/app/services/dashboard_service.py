"""仪表盘聚合服务：一次请求返回首页/概览所需的全部数据。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.cache import cache
from app.models.task import DdlTask
from app.services import (classroom_service, course_service, finance_service, health_service,
                          kaoyan_service, knowledge_service, study_service, task_service)


def build_summary(db: Session, user, *, days: int = 7) -> dict:
    """汇总课程/任务/学习/考研/知识/财务/健康/教室，供 AI 工具与前端共用。"""
    key = f"polaris:dashboard:{user.id}:{date.today().isoformat()}"
    cached = cache.get(key)
    if cached:
        return cached

    courses_today = course_service.today_classes(db, user.id)
    task_stats = task_service.stats(db, user.id, days=days)
    upcoming = [t.to_dict() for t in task_service.upcoming(db, user.id, within_days=7, limit=8)]
    today_due = [t.to_dict() for t in task_service.today_due(db, user.id)]
    study = study_service.stats(db, user.id, days=days)
    finance = finance_service.summary(db, user.id)
    health = health_service.report(db, user.id, days=days)
    kaoyan = _kaoyan_overview(db, user.id)
    knowledge = knowledge_service.stats(db, user.id)
    classroom = classroom_service.today_stats(db)

    config = user.config or {}
    alerts = []
    if task_stats["overdue"]:
        alerts.append({"tone": "red", "tag": "DDL", "text": f"有 {task_stats['overdue']} 项任务已逾期"})
    if task_stats["due_today"]:
        alerts.append({"tone": "yellow", "tag": "DDL",
                       "text": f"今日 {task_stats['due_today']} 项任务到期，注意优先级"})
    if health["sedentary"]["should_break"]:
        alerts.append({"tone": "yellow", "tag": "健康",
                       "text": health["sedentary"]["message"]})
    if study["streak_days"]:
        alerts.append({"tone": "green", "tag": "学习",
                       "text": f"已连续学习打卡 {study['streak_days']} 天，保持节奏"})
    if kaoyan.get("has_target"):
        alerts.append({"tone": "blue", "tag": "考研",
                       "text": f"距初试 {kaoyan['days_left']} 天，总分差 {kaoyan['total_gap']} 分"})
    if knowledge["vector_pending"]:
        alerts.append({"tone": "blue", "tag": "知识库",
                       "text": f"{knowledge['vector_pending']} 篇文档待向量化"})

    summary = {
        "date": date.today().isoformat(),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "profile": {
            "nickname": user.nickname or user.username,
            "school": config.get("school", "华中科技大学"),
            "role": config.get("role", "考研备战中"),
        },
        "courses_today": courses_today,
        "next_class": next((c for c in courses_today if c["status"] in {"current", "upcoming"}), None),
        "tasks": task_stats,
        "today_due": today_due,
        "upcoming_tasks": upcoming,
        "study": {
            "days": days,
            "total_hours": study["total_hours"],
            "avg_minutes_per_day": study["avg_minutes_per_day"],
            "streak_days": study["streak_days"],
            "daily": study["daily"],
            "by_subject": study["by_subject"],
        },
        "kaoyan": kaoyan,
        "knowledge": {
            "doc_count": knowledge["doc_count"],
            "chunk_count": knowledge["chunk_count"],
            "coverage": knowledge["coverage"],
            "new_this_week": knowledge["new_this_week"],
            "hot_tags": knowledge["hot_tags"][:6],
        },
        "finance": {
            "month": finance["month"],
            "income": finance["income"],
            "expense": finance["expense"],
            "balance": finance["balance"],
            "study_expense": finance["study_expense"],
            "study_ratio": finance["study_ratio"],
            "categories": finance["categories"][:6],
        },
        "health": {
            "sedentary": health["sedentary"],
            "avg_sleep_hours": health["avg_sleep_hours"],
            "week_exercise_minutes": health["week_exercise_minutes"],
            "tips": health["tips"],
        },
        "classroom": classroom,
        "alerts": alerts[:6],
    }
    cache.set(key, summary, ttl=60)
    return summary


def _kaoyan_overview(db: Session, user_id: int) -> dict:
    target = kaoyan_service.get_active_target(db, user_id)
    if not target:
        return {"has_target": False}
    gap = target.gap_analysis or kaoyan_service.gap_analysis(db, target)
    phases = target.phases
    return {
        "has_target": True,
        "school": target.school,
        "major": target.major,
        "degree_type": target.degree_type,
        "exam_date": target.exam_date.isoformat() if target.exam_date else None,
        "days_left": gap.get("days_left"),
        "total_target": target.total_target,
        "total_current": target.total_current,
        "total_gap": gap.get("total_gap"),
        "progress": gap.get("progress"),
        "focus_subjects": gap.get("focus_subjects", []),
        "subjects": gap.get("subjects", []),
        "phase_progress": round(sum(p.progress for p in phases) / len(phases), 1) if phases else 0,
    }


def invalidate(user_id: int) -> None:
    cache.delete_prefix(f"polaris:dashboard:{user_id}")
