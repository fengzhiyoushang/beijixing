"""全局 AI 助手 Function Call 工具注册表。

每个工具在服务端以当前 JWT 用户身份执行，天然实现数据权限隔离；
覆盖课表/DDL/打卡/空教室/财务/考研/知识库/健康/总览九大域。
"""
import json
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List

from sqlalchemy.orm import Session

from app import models as m
from app.services import classroom as classroom_svc
from app.services import dashboard as dash_svc
from app.services import health_svc, rag
from app.utils.timeutil import month_str


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    return None


# ────────────────────────── 处理函数 ──────────────────────────
def h_today_schedule(db, uid, args):
    return {"date": date.today().isoformat(), "classes": dash_svc.today_classes(db, uid)}


def h_week_schedule(db, uid, args):
    courses = db.query(m.Course).filter(m.Course.user_id == uid).all()
    grid: Dict[int, list] = {wd: [] for wd in range(1, 8)}
    for c in courses:
        for s in c.slots:
            grid[s.weekday].append({**s.to_dict(), "course": c.name, "location": c.location, "color": c.color})
    for wd in grid:
        grid[wd].sort(key=lambda x: x["start_time"])
    return {"week": [{"weekday": wd, "classes": grid[wd]} for wd in range(1, 8)]}


def h_list_tasks(db, uid, args):
    q = db.query(m.Task).filter(m.Task.user_id == uid, m.Task.status != "canceled")
    if args.get("status"):
        q = q.filter(m.Task.status == args["status"])
    if args.get("category"):
        q = q.filter(m.Task.category == args["category"])
    within = args.get("within_days")
    now = datetime.now()
    if within:
        q = q.filter(m.Task.due_at.isnot(None), m.Task.due_at <= now + timedelta(days=float(within)))
    tasks = q.order_by(m.Task.due_at).all()[:20]
    return {"count": len(tasks), "tasks": [t.to_dict(now) for t in tasks]}


def h_create_task(db, uid, args):
    task = m.Task(
        user_id=uid,
        title=str(args.get("title") or "未命名任务")[:200],
        description=args.get("description"),
        category=args.get("category", "study"),
        priority=args.get("priority", "medium"),
        due_at=_parse_dt(args.get("due_at")),
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"created": task.to_dict()}


def h_complete_task(db, uid, args):
    q = db.query(m.Task).filter(m.Task.user_id == uid, m.Task.status == "pending")
    if args.get("task_id"):
        task = q.filter(m.Task.id == int(args["task_id"])).first()
    else:
        key = str(args.get("title", ""))
        task = q.filter(m.Task.title.contains(key)).order_by(m.Task.due_at).first()
    if not task:
        return {"error": "未找到匹配的待办任务"}
    task.status = "done"
    task.done_at = datetime.now()
    task.progress = 100
    db.commit()
    return {"completed": task.to_dict()}


def h_checkin(db, uid, args):
    rec = m.CheckinRecord(
        user_id=uid,
        subject=str(args.get("subject") or "自习")[:64],
        minutes=int(args.get("minutes") or 0),
        content=args.get("content"),
        date=date.today(),
    )
    db.add(rec)
    db.commit()
    return {"created": rec.to_dict(), "stats": dash_svc.checkin_stats(db, uid)}


def h_checkin_stats(db, uid, args):
    return dash_svc.checkin_stats(db, uid)


def h_classroom_predict(db, uid, args):
    weekday = int(args["weekday"]) if args.get("weekday") else None
    hour = int(args["hour"]) if args.get("hour") is not None else None
    return classroom_svc.predict(db, uid, weekday, hour)


def h_classroom_records(db, uid, args):
    recs = (
        db.query(m.ClassroomRecord)
        .filter(m.ClassroomRecord.user_id == uid)
        .order_by(m.ClassroomRecord.id.desc())
        .limit(10)
        .all()
    )
    return {"records": [r.to_dict() for r in recs]}


def h_finance_summary(db, uid, args):
    month = args.get("month") or month_str(date.today())
    return dash_svc.finance_month_summary(db, uid, month)


def h_finance_add(db, uid, args):
    rec = m.FinanceRecord(
        user_id=uid,
        type="expense" if args.get("type", "expense") == "expense" else "income",
        category=str(args.get("category") or "其他")[:32],
        amount=float(args.get("amount") or 0),
        is_study=bool(args.get("is_study")),
        note=args.get("note"),
        occurred_at=date.today(),
    )
    db.add(rec)
    db.commit()
    return {"created": rec.to_dict()}


def h_kaoyan_progress(db, uid, args):
    return {"kaoyan": dash_svc.kaoyan_overview(db, uid)}


def h_knowledge_search(db, uid, args):
    question = str(args.get("question") or "")
    hits = rag.search(db, uid, question, top_k=5)
    for h in hits:
        doc = db.get(m.KnowledgeDoc, h["doc_id"])
        if doc:
            doc.read_count = (doc.read_count or 0) + 1
    db.commit()
    return {"hits": hits, "note": "回答时请标注引用的资料编号"}


def h_dashboard_summary(db, uid, args):
    user = db.get(m.User, uid)
    summary = dash_svc.build_summary(db, user)
    summary.pop("charts", None)  # 节省 token，图表数据 AI 用不到
    return summary


def h_health_status(db, uid, args):
    since = date.today() - timedelta(days=6)
    logs = db.query(m.HealthLog).filter(m.HealthLog.user_id == uid, m.HealthLog.date >= since).all()
    sleeps = [l.minutes for l in logs if l.kind == "sleep" and l.minutes]
    return {
        "sedentary": health_svc.sedentary_status(db, uid),
        "week_sleep_avg_min": int(sum(sleeps) / len(sleeps)) if sleeps else None,
        "week_exercise_minutes": sum(l.minutes or 0 for l in logs if l.kind == "exercise"),
        "week_water_ml": sum(int(l.value or 0) for l in logs if l.kind == "water"),
    }


def h_health_log(db, uid, args):
    kind = str(args.get("kind") or "other")
    log = m.HealthLog(
        user_id=uid,
        kind=kind,
        happened_at=datetime.now(),
        date=date.today(),
        minutes=int(args["minutes"]) if args.get("minutes") else None,
        value=float(args["value"]) if args.get("value") else None,
        note=args.get("note"),
    )
    db.add(log)
    db.commit()
    return {"created": log.to_dict()}


HANDLERS: Dict[str, Callable] = {
    "get_today_schedule": h_today_schedule,
    "list_week_schedule": h_week_schedule,
    "list_tasks": h_list_tasks,
    "create_task": h_create_task,
    "complete_task": h_complete_task,
    "checkin_study": h_checkin,
    "get_checkin_stats": h_checkin_stats,
    "predict_free_classroom": h_classroom_predict,
    "get_classroom_records": h_classroom_records,
    "get_finance_summary": h_finance_summary,
    "add_finance_record": h_finance_add,
    "get_kaoyan_progress": h_kaoyan_progress,
    "knowledge_search": h_knowledge_search,
    "get_dashboard_summary": h_dashboard_summary,
    "get_health_status": h_health_status,
    "log_health": h_health_log,
}


def _fn(name: str, desc: str, props: Dict[str, Any], required: List[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": props, "required": required or []},
        },
    }


STR = {"type": "string"}
INT = {"type": "integer"}
BOOL = {"type": "boolean"}

TOOL_SPECS: List[dict] = [
    _fn("get_today_schedule", "查询用户今天的课程安排（含上课地点与状态）", {}),
    _fn("list_week_schedule", "查询用户本周完整课表", {}),
    _fn("list_tasks", "查询 DDL 任务。可按状态/分类过滤，或限定即将到期的天数范围", {
        "status": {"type": "string", "enum": ["pending", "done"]},
        "category": {"type": "string", "enum": ["study", "work", "life"]},
        "within_days": {"type": "integer", "description": "只看 N 天内到期"},
    }),
    _fn("create_task", "新建 DDL 任务", {
        "title": STR, "description": STR,
        "category": {"type": "string", "enum": ["study", "work", "life"]},
        "priority": {"type": "string", "enum": ["high", "medium", "low"]},
        "due_at": {"type": "string", "description": "ISO 或 YYYY-MM-DD HH:MM"},
    }, ["title"]),
    _fn("complete_task", "把任务标记为已完成（按 id 或标题模糊匹配）", {"task_id": INT, "title": STR}),
    _fn("checkin_study", "帮用户记录一次学习打卡", {"subject": STR, "minutes": INT, "content": STR}, ["subject", "minutes"]),
    _fn("get_checkin_stats", "查询打卡统计：连续天数、今日/本周学习分钟、科目分布", {}),
    _fn("predict_free_classroom", "预测指定时段哪些教室空闲概率最高（基于历史拍照数据+课程占用）", {
        "weekday": {"type": "integer", "minimum": 1, "maximum": 7}, "hour": {"type": "integer", "minimum": 0, "maximum": 23},
    }),
    _fn("get_classroom_records", "查询最近的空教室拍照采集记录", {}),
    _fn("get_finance_summary", "查询某月收支汇总与学习投入分析，month 形如 2025-08，缺省为本月", {"month": STR}),
    _fn("add_finance_record", "记一笔收支", {
        "type": {"type": "string", "enum": ["income", "expense"]},
        "amount": {"type": "number"}, "category": STR, "is_study": BOOL, "note": STR,
    }, ["type", "amount"]),
    _fn("get_kaoyan_progress", "查询考研目标进度：剩余天数、分数差距、每日任务完成率", {}),
    _fn("knowledge_search", "在用户知识库中检索与问题相关的资料片段（RAG），回答个人笔记类问题必须调用", {
        "question": STR,
    }, ["question"]),
    _fn("get_dashboard_summary", "获取用户整体状态总览（课程/任务/打卡/财务/目标/健康）", {}),
    _fn("get_health_status", "查询健康状态：久坐提醒、本周睡眠/运动/饮水", {}),
    _fn("log_health", "记录一条健康数据：sleep(含 minutes 小时*60)/water(value ml)/exercise(minutes)/other", {
        "kind": {"type": "string", "enum": ["sleep", "wake", "sedentary", "water", "exercise", "other"]},
        "minutes": INT, "value": {"type": "number"}, "note": STR,
    }, ["kind"]),
]


def execute(db: Session, user_id: int, name: str, args: Dict[str, Any] | None) -> dict:
    handler = HANDLERS.get(name)
    if handler is None:
        return {"error": f"未知工具: {name}"}
    try:
        return handler(db, user_id, args or {})
    except Exception as exc:  # 工具失败不打断对话循环
        return {"error": f"工具执行失败: {type(exc).__name__}: {exc}"}


def summarize(result: dict, limit: int = 160) -> str:
    text = json.dumps(result, ensure_ascii=False, default=str)
    return text[:limit] + ("…" if len(text) > limit else "")
