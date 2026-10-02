"""仪表盘聚合与跨模块统计助手：Dashboard 视图 / AI 工具 / 小程序首页共用。"""
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app import models as m
from app.services.health_svc import sedentary_status
from app.utils.timeutil import month_str, parse_month


# ──────────────── 课程 ────────────────
def today_classes(db: Session, user_id: int, d: date | None = None) -> list[dict]:
    d = d or date.today()
    rows = (
        db.query(m.ClassSlot, m.Course)
        .join(m.Course, m.ClassSlot.course_id == m.Course.id)
        .filter(m.Course.user_id == user_id, m.ClassSlot.weekday == d.isoweekday())
        .order_by(m.ClassSlot.start_time)
        .all()
    )
    now_hm = datetime.now().strftime("%H:%M")
    out = []
    for slot, course in rows:
        if now_hm > slot.end_time:
            status = "past"
        elif now_hm >= slot.start_time:
            status = "ongoing"
        else:
            status = "upcoming"
        out.append({
            **slot.to_dict(),
            "course_id": course.id,
            "course": course.name,
            "teacher": course.teacher,
            "location": course.location,
            "color": course.color,
            "class_status": status,
        })
    return out


# ──────────────── 打卡 ────────────────
def checkin_stats(db: Session, user_id: int) -> dict:
    since = date.today() - timedelta(days=60)
    recs = (
        db.query(m.CheckinRecord)
        .filter(m.CheckinRecord.user_id == user_id, m.CheckinRecord.date >= since)
        .all()
    )
    days = sorted({r.date for r in recs}, reverse=True)
    streak = 0
    cursor = date.today()
    if days and days[0] == cursor - timedelta(days=1):
        cursor -= timedelta(days=1)
    if not days or days[0] != cursor:
        streak = 0
    else:
        dset = set(days)
        while cursor in dset:
            streak += 1
            cursor -= timedelta(days=1)

    subject_minutes: dict[str, int] = defaultdict(int)
    for r in recs:
        subject_minutes[r.subject] += r.minutes

    recent14 = []
    for i in range(13, -1, -1):
        d = date.today() - timedelta(days=i)
        recent14.append({
            "date": d.isoformat(),
            "minutes": sum(r.minutes for r in recs if r.date == d),
        })

    return {
        "streak_days": streak,
        "today_minutes": sum(r.minutes for r in recs if r.date == date.today()),
        "week_minutes": sum(r.minutes for r in recs if r.date >= date.today() - timedelta(days=6)),
        "total_minutes": sum(r.minutes for r in recs),
        "subjects": sorted(
            [{"subject": k, "minutes": v} for k, v in subject_minutes.items()],
            key=lambda x: -x["minutes"],
        )[:8],
        "trend14": recent14,
    }


# ──────────────── 任务 ────────────────
def task_stats(db: Session, user_id: int) -> dict:
    now = datetime.now()
    tasks = (
        db.query(m.Task)
        .filter(m.Task.user_id == user_id, m.Task.status != "canceled")
        .all()
    )
    pending = [t for t in tasks if t.status == "pending"]
    done = [t for t in tasks if t.status == "done"]
    overdue = [t for t in pending if t.due_at and t.due_at < now]
    due_today = [t for t in pending if t.due_at and t.due_at.date() == now.date()]

    by_category: dict[str, dict] = defaultdict(lambda: {"pending": 0, "done": 0})
    for t in tasks:
        by_category[t.category]["pending" if t.status == "pending" else "done"] += 1

    trend14 = []
    for i in range(13, -1, -1):
        d = now.date() - timedelta(days=i)
        trend14.append({
            "date": d.isoformat(),
            "done": sum(1 for t in done if t.done_at and t.done_at.date() == d),
        })

    return {
        "total": len(tasks),
        "pending": len(pending),
        "done": len(done),
        "overdue": len(overdue),
        "due_today": len(due_today),
        "completion_rate": round(len(done) / len(tasks), 3) if tasks else 0,
        "by_category": dict(by_category),
        "trend14": trend14,
    }


# ──────────────── 财务 ────────────────
def finance_month_summary(db: Session, user_id: int, month: str) -> dict:
    start, end = parse_month(month)
    recs = (
        db.query(m.FinanceRecord)
        .filter(
            m.FinanceRecord.user_id == user_id,
            m.FinanceRecord.occurred_at >= start,
            m.FinanceRecord.occurred_at < end,
        )
        .all()
    )
    income = sum(r.amount for r in recs if r.type == "income")
    expense = sum(r.amount for r in recs if r.type == "expense")
    by_cat: dict[str, float] = defaultdict(float)
    for r in recs:
        if r.type == "expense":
            by_cat[r.category] += r.amount
    study = sum(
        r.amount for r in recs
        if r.type == "expense" and (r.is_study or r.category in ("学习", "书籍", "课程"))
    )
    return {
        "month": month,
        "income": round(income, 2),
        "expense": round(expense, 2),
        "balance": round(income - expense, 2),
        "study_expense": round(study, 2),
        "study_ratio": round(study / expense, 3) if expense else 0,
        "categories": sorted(
            [{"category": k, "amount": round(v, 2)} for k, v in by_cat.items()],
            key=lambda x: -x["amount"],
        ),
    }


# ──────────────── 考研 ────────────────
def kaoyan_overview(db: Session, user_id: int) -> dict | None:
    goal = (
        db.query(m.KaoyanGoal)
        .filter(m.KaoyanGoal.user_id == user_id, m.KaoyanGoal.status == "active")
        .order_by(m.KaoyanGoal.id.desc())
        .first()
    )
    if not goal:
        return None
    phases = goal.phases
    tasks = [t for p in phases for t in p.tasks]
    done_rate = round(sum(1 for t in tasks if t.done) / len(tasks), 3) if tasks else None
    days_left = (goal.exam_date - date.today()).days if goal.exam_date else None
    return {
        "goal_id": goal.id,
        "target_school": goal.target_school,
        "target_major": goal.target_major,
        "exam_date": goal.exam_date.isoformat() if goal.exam_date else None,
        "days_left": days_left,
        "total_target": goal.total_target,
        "total_current": goal.total_current,
        "gap": round(goal.total_target - goal.total_current, 1),
        "score_rate": round(goal.total_current / goal.total_target, 3) if goal.total_target else 0,
        "phase_count": len(phases),
        "daily_task_done_rate": done_rate,
    }


# ──────────────── 聚合 ────────────────
def build_summary(db: Session, user: m.User) -> dict:
    now = datetime.now()
    classes = today_classes(db, user.id)
    ts = task_stats(db, user.id)
    cs = checkin_stats(db, user.id)
    fin = finance_month_summary(db, user.id, month_str(now.date()))
    goal = kaoyan_overview(db, user.id)
    sed = sedentary_status(db, user.id)

    pending = (
        db.query(m.Task)
        .filter(m.Task.user_id == user.id, m.Task.status == "pending",
                m.Task.due_at.isnot(None))
        .order_by(m.Task.due_at)
        .all()
    )
    upcoming = [t.to_dict(now) for t in pending if t.due_at >= now][:5]

    sleep_y = (
        db.query(m.HealthLog)
        .filter(
            m.HealthLog.user_id == user.id,
            m.HealthLog.kind == "sleep",
            m.HealthLog.date == now.date() - timedelta(days=1),
        )
        .order_by(m.HealthLog.id.desc())
        .first()
    )

    next_class = next((c for c in classes if c["class_status"] == "upcoming"), None)

    alerts = []
    if ts["overdue"]:
        alerts.append({"level": "danger", "text": f"{ts['overdue']} 个 DDL 已逾期，尽快处理", "link": "/tasks"})
    if next_class:
        alerts.append({"level": "info", "text": f"下一节：{next_class['course']} @ {next_class['location'] or '待定'}（{next_class['start_time']}）", "link": "/timetable"})
    if sed.get("should_break"):
        alerts.append({"level": "warning", "text": sed["message"], "link": "/health"})
    if not cs["today_minutes"]:
        alerts.append({"level": "info", "text": "今天还没有学习打卡，开始第一个专注时段吧", "link": "/checkin"})

    return {
        "date": now.date().isoformat(),
        "weekday": now.isoweekday(),
        "nickname": user.nickname,
        "classes_today": classes,
        "tasks": ts,
        "upcoming_tasks": upcoming,
        "checkin": cs,
        "finance": fin,
        "kaoyan": goal,
        "health": {
            "sedentary": sed,
            "sleep_yesterday_minutes": sleep_y.minutes if sleep_y else None,
        },
        "alerts": alerts,
        "charts": {
            "task_trend14": ts["trend14"],
            "checkin_trend14": cs["trend14"],
            "expense_categories": fin["categories"],
        },
    }
