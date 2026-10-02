"""Function Call 工具注册表：把系统能力暴露给 DeepSeek。

每个工具 = OpenAI function schema（TOOL_SPECS）+ 服务端处理器（HANDLERS）。
处理器统一签名 `(db, user, args) -> dict`，异常会被包装为 {"ok": False, "error": ...}。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.exceptions import AppError
from app.schemas.classroom import StatusReportIn
from app.schemas.finance import FinanceRecordIn
from app.schemas.health import HealthRecordIn
from app.schemas.study import StudyRecordIn
from app.schemas.task import TaskIn
from app.services import (classroom_service, course_service, dashboard_service, finance_service,
                          health_service, kaoyan_service, knowledge_service, study_service,
                          task_service)

logger = logging.getLogger("polaris.tools")

HANDLERS: dict[str, Callable[..., Any]] = {}


def tool(name: str, description: str, parameters: dict):
    """装饰器：注册工具处理器。"""
    def wrapper(func: Callable[..., Any]):
        HANDLERS[name] = func
        _SPECS.append({
            "type": "function",
            "function": {"name": name, "description": description, "parameters": parameters},
        })
        return func
    return wrapper


_SPECS: list[dict] = []


def specs() -> list[dict]:
    return list(_SPECS)


def tool_names() -> list[str]:
    return list(HANDLERS.keys())


def _obj(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or []}


_STR = {"type": "string"}
_INT = {"type": "integer"}
_NUM = {"type": "number"}
_BOOL = {"type": "boolean"}


# ═══════════════ 概览 ═══════════════
@tool("get_dashboard_summary", "获取用户今日总览：今日课程、待办 DDL、学习时长、考研进度、财务概况、健康提醒",
      _obj({"days": {**_INT, "description": "统计天数，默认 7"}}))
def get_dashboard_summary(db: Session, user, args: dict) -> dict:
    summary = dashboard_service.build_summary(db, user, days=int(args.get("days") or 7))
    return {
        "date": summary["date"],
        "next_class": summary["next_class"],
        "courses_today": [{"time": f"{c['start_time']}-{c['end_time']}", "name": c["name"],
                           "room": c["location"], "status": c["status"]} for c in summary["courses_today"]],
        "tasks": {k: summary["tasks"][k] for k in ("pending", "due_today", "overdue", "completion_rate")},
        "due_today": [{"title": t["title"], "priority": t["priority"], "due_at": t["due_at"]}
                      for t in summary["today_due"]],
        "study": {k: summary["study"][k] for k in ("total_hours", "avg_minutes_per_day", "streak_days")},
        "kaoyan": summary["kaoyan"],
        "finance": summary["finance"],
        "health": summary["health"],
        "alerts": summary["alerts"],
    }


# ═══════════════ 课程表 ═══════════════
@tool("query_schedule", "查询课表：可查今天/某天/整周课程（含时间、课程名、教室、教师）",
      _obj({"scope": {**_STR, "enum": ["today", "week"], "description": "today=今日，week=整周"},
           "week": {**_INT, "description": "教学周次，缺省为当前周"}}))
def query_schedule(db: Session, user, args: dict) -> dict:
    scope = args.get("scope") or "today"
    if scope == "week":
        data = course_service.week_timetable(db, user.id, week=args.get("week"))
        return {"week": data["week"], "total_classes": data["total_classes"],
                "days": [{"weekday": d["weekday"], "classes": [
                    {"time": f"{c['start_time']}-{c['end_time']}", "name": c["name"],
                     "room": c["location"], "teacher": c["teacher"]} for c in d["classes"]]}
                    for d in data["days"]]}
    classes = course_service.today_classes(db, user.id)
    return {"date": date.today().isoformat(),
            "classes": [{"time": f"{c['start_time']}-{c['end_time']}", "name": c["name"],
                         "room": c["location"], "teacher": c["teacher"], "status": c["status"]}
                        for c in classes]}


# ═══════════════ DDL 任务 ═══════════════
@tool("add_ddl_task", "新增一个 DDL 任务（待办事项），支持优先级、分类、截止时间与关联课程",
      _obj({"title": {**_STR, "description": "任务标题"},
           "due_at": {**_STR, "description": "截止时间，格式 YYYY-MM-DD HH:MM 或 YYYY-MM-DD"},
           "priority": {**_STR, "enum": ["high", "medium", "low"]},
           "category": {**_STR, "description": "分类，如 学习/课程/考研/生活"},
           "description": _STR,
           "estimate_minutes": {**_INT, "description": "预计耗时（分钟）"}},
          ["title"]))
def add_ddl_task(db: Session, user, args: dict) -> dict:
    due = _parse_due(args.get("due_at"))
    payload = TaskIn(
        title=args["title"], description=args.get("description"),
        category=args.get("category") or "学习", priority=args.get("priority") or "medium",
        due_at=due, estimate_minutes=int(args.get("estimate_minutes") or 0), source="ai",
    )
    task = task_service.create_task(db, user.id, payload)
    dashboard_service.invalidate(user.id)
    return {"ok": True, "task": task.to_dict()}


@tool("list_ddl_tasks", "查询 DDL 任务列表，可按状态、分类、优先级、关键词筛选",
      _obj({"status": {**_STR, "enum": ["pending", "done", "archived"]},
           "category": _STR, "priority": {**_STR, "enum": ["high", "medium", "low"]},
           "keyword": _STR, "limit": {**_INT, "description": "返回条数，默认 10"}}))
def list_ddl_tasks(db: Session, user, args: dict) -> dict:
    tasks = task_service.list_tasks(
        db, user.id, status=args.get("status"), category=args.get("category"),
        priority=args.get("priority"), keyword=args.get("keyword"), order="priority",
    )[: int(args.get("limit") or 10)]
    return {"count": len(tasks),
            "tasks": [{"id": t.id, "title": t.title, "priority": t.priority, "status": t.status,
                       "category": t.category, "due_at": t.to_dict()["due_at"],
                       "remaining_seconds": t.to_dict()["remaining_seconds"],
                       "overdue": t.overdue} for t in tasks]}


@tool("complete_ddl_task", "把某个 DDL 任务标记为已完成；可用 id 或标题关键词定位",
      _obj({"task_id": _INT, "title_keyword": {**_STR, "description": "标题关键词(模糊匹配)"}},
           []))
def complete_ddl_task(db: Session, user, args: dict) -> dict:
    task_id = args.get("task_id")
    if not task_id:
        keyword = args.get("title_keyword") or ""
        candidates = task_service.list_tasks(db, user.id, status="pending", keyword=keyword)
        if not candidates:
            return {"ok": False, "error": f"未找到标题包含「{keyword}」的待办任务"}
        task_id = candidates[0].id
    task = task_service.complete_task(db, user.id, int(task_id))
    dashboard_service.invalidate(user.id)
    return {"ok": True, "completed": task.title}


@tool("get_task_stats", "获取任务统计：待办数、今日到期、逾期、完成率、分类分布、近 7 天趋势",
      _obj({"days": {**_INT, "description": "趋势天数，默认 7"}}))
def get_task_stats(db: Session, user, args: dict) -> dict:
    return task_service.stats(db, user.id, days=int(args.get("days") or 7))


# ═══════════════ 学习记录 ═══════════════
@tool("log_study_record", "记录一次学习（科目、时长、内容），用于学习时长统计与打卡",
      _obj({"subject": {**_STR, "description": "科目，如 数学/英语/408/政治"},
           "minutes": {**_INT, "description": "学习时长（分钟）"},
           "content": {**_STR, "description": "学习内容"},
           "date": {**_STR, "description": "日期 YYYY-MM-DD，缺省今天"},
           "mock_name": {**_STR, "description": "若有模考，填写模考名称"},
           "mock_score": _NUM, "mock_full_score": _NUM},
          ["subject", "minutes"]))
def log_study_record(db: Session, user, args: dict) -> dict:
    payload = StudyRecordIn(
        subject=args["subject"], minutes=int(args["minutes"]),
        content=args.get("content"), date=_parse_due(args.get("date"), day_only=True),
        mock_name=args.get("mock_name"),
        mock_score=args.get("mock_score"), mock_full_score=args.get("mock_full_score"),
    )
    record = study_service.create_record(db, user.id, payload)
    dashboard_service.invalidate(user.id)
    return {"ok": True, "record": record.to_dict()}


@tool("get_study_progress", "获取学习进度：近 N 天总时长、日均、连续打卡、科目分布、模考成绩",
      _obj({"days": {**_INT, "description": "统计天数，默认 7"}}))
def get_study_progress(db: Session, user, args: dict) -> dict:
    data = study_service.stats(db, user.id, days=int(args.get("days") or 7))
    return {
        "total_hours": data["total_hours"], "avg_minutes_per_day": data["avg_minutes_per_day"],
        "streak_days": data["streak_days"], "active_days": data["active_days"],
        "by_subject": data["by_subject"][:6], "mock_scores": data["mock_scores"][-3:],
        "task_progress": data["task_progress"], "daily": data["daily"],
    }


# ═══════════════ 空教室 ═══════════════
@tool("classroom_predict", "预测某时段空闲教室（基于历史上报 + 时间衰减 + 课程占用惩罚）",
      _obj({"weekday": {**_INT, "description": "1~7，缺省今天"},
           "hour": {**_INT, "description": "0~23，缺省当前小时"},
           "limit": {**_INT, "description": "返回条数，默认 5"}}))
def classroom_predict(db: Session, user, args: dict) -> dict:
    data = classroom_service.predict(
        db, user.id, weekday=args.get("weekday"), hour=args.get("hour"),
        limit=int(args.get("limit") or 5),
    )
    return {"weekday": data["weekday"], "hour": data["hour"],
            "results": [{"name": r["name"], "confidence": r["confidence"],
                         "samples": r["samples"], "last_status": r["last_status"]}
                        for r in data["results"]],
            "hint": data.get("hint")}


@tool("report_classroom_status", "上报教室当前状态（空闲/占用），作为空闲预测的数据来源",
      _obj({"building": {**_STR, "description": "教学楼，如 东一舍"},
           "room_no": {**_STR, "description": "教室号，如 A305"},
           "status": {**_STR, "enum": ["free", "busy", "unknown"]},
           "note": _STR,
           "occupied_seats": _INT},
          ["building", "room_no", "status"]))
def report_classroom_status(db: Session, user, args: dict) -> dict:
    payload = StatusReportIn(
        building=args["building"], room_no=args["room_no"], status=args["status"],
        note=args.get("note"), occupied_seats=int(args.get("occupied_seats") or 0),
        source="ai",
    )
    log = classroom_service.report_status(db, user.id, payload)
    dashboard_service.invalidate(user.id)
    return {"ok": True, "log": log.to_dict()}


@tool("classroom_free_rate", "查询某间教室的时段空闲率矩阵（周一~周日 × 8:00~22:00）",
      _obj({"building": {**_STR}, "room_no": {**_STR}}, ["building", "room_no"]))
def classroom_free_rate(db: Session, user, args: dict) -> dict:
    data = classroom_service.free_rate(db, building=args["building"], room_no=args["room_no"])
    best = data["best_slot"]
    return {"name": data["name"], "samples": data["samples"], "avg_rate": data["avg_rate"],
            "enough_data": data["enough_data"],
            "best_slot": {"weekday": best["weekday"], "hour": best["hour"], "rate": best["rate"]}
            if best else None}


# ═══════════════ 考研 ═══════════════
@tool("get_kaoyan_gap", "获取考研目标差距分析：各科当前/目标分、差距、提分优先级、剩余天数",
      _obj({}))
def get_kaoyan_gap(db: Session, user, args: dict) -> dict:
    target = kaoyan_service.get_active_target(db, user.id)
    if not target:
        return {"ok": False, "error": "尚未录入考研目标，请先在「考研规划」中设置院校与分数线"}
    return kaoyan_service.gap_analysis(db, target)


@tool("generate_kaoyan_plan", "根据考研目标和当前成绩生成阶段学习计划与每日任务拆解",
      _obj({"total_weeks": {**_INT, "description": "剩余备考周数"},
           "daily_minutes": {**_INT, "description": "每日可投入分钟数"},
           "use_ai": {**_BOOL, "description": "是否用 DeepSeek 生成（默认 true，失败回退规则引擎）"}}))
async def generate_kaoyan_plan(db: Session, user, args: dict) -> dict:
    from app.schemas.kaoyan import PlanGenerateIn

    payload = PlanGenerateIn(
        total_weeks=int(args.get("total_weeks") or 16),
        daily_minutes=int(args.get("daily_minutes") or 300),
        use_ai=bool(args.get("use_ai", True)),
    )
    return await kaoyan_service.generate_plan(db, user.id, payload)


@tool("record_kaoyan_score", "录入某科目最新成绩（模考分数），自动更新总分与差距分析",
      _obj({"subject": {**_STR}, "current": {**_NUM, "description": "最新得分"},
           "mock_name": _STR, "add_study_record": _BOOL},
          ["subject", "current"]))
def record_kaoyan_score(db: Session, user, args: dict) -> dict:
    from app.schemas.kaoyan import ScoreIn

    payload = ScoreIn(subject=args["subject"], current=float(args["current"]),
                      mock_name=args.get("mock_name"),
                      add_study_record=bool(args.get("add_study_record", False)))
    result = kaoyan_service.record_score(db, user.id, payload)
    dashboard_service.invalidate(user.id)
    return {"ok": True, "gap_analysis": result["gap_analysis"]}


# ═══════════════ 知识库 ═══════════════
@tool("search_knowledge", "在个人知识库中检索文档（关键词 + 向量混合检索）",
      _obj({"keyword": {**_STR, "description": "检索词"},
           "top_k": {**_INT, "description": "返回条数，默认 5"}}, ["keyword"]))
def search_knowledge(db: Session, user, args: dict) -> dict:
    from app.ai import rag

    hits = rag.search(db, user.id, args["keyword"], top_k=int(args.get("top_k") or 5))
    docs = rag.keyword_search_docs(db, user.id, args["keyword"], limit=5)
    return {
        "chunks": [{"doc": h["doc_title"], "score": h["score"], "content": h["content"][:200]}
                   for h in hits],
        "docs": [{"id": d["id"], "title": d["title"], "hits": d["hits"], "snippet": d["snippet"][:200]}
                 for d in docs],
    }


@tool("rag_answer", "基于个人知识库回答问题（RAG：检索 → 组装 prompt → DeepSeek 生成，附引用）",
      _obj({"question": {**_STR, "description": "要提问的问题"},
           "top_k": {**_INT, "description": "检索片段数，默认 5"}}, ["question"]))
async def rag_answer(db: Session, user, args: dict) -> dict:
    from app.ai import rag

    result = await rag.answer(db, user, args["question"], top_k=int(args.get("top_k") or 5))
    return {"answer": result["answer"], "mode": result["mode"],
            "references": result["references"]}


# ═══════════════ 财务 ═══════════════
@tool("add_finance_record", "记一笔收入或支出（支持标记为学习投入）",
      _obj({"type": {**_STR, "enum": ["income", "expense"]},
           "category": {**_STR, "description": "分类，如 餐饮/交通/学习投入"},
           "amount": {**_NUM, "description": "金额（正数）"},
           "note": _STR, "is_study": {**_BOOL, "description": "是否为学习投入"}},
          ["type", "amount"]))
def add_finance_record(db: Session, user, args: dict) -> dict:
    payload = FinanceRecordIn(
        type=args["type"], category=args.get("category") or ("学习投入" if args.get("is_study") else "其他"),
        amount=float(args["amount"]), note=args.get("note"),
        is_study=bool(args.get("is_study", False)),
    )
    record = finance_service.create_record(db, user.id, payload)
    dashboard_service.invalidate(user.id)
    return {"ok": True, "record": record.to_dict()}


@tool("get_finance_summary", "获取财务汇总：收入、支出、结余、学习投入占比、分类明细、预算执行",
      _obj({"month": {**_STR, "description": "YYYY-MM，缺省本月"}}))
def get_finance_summary(db: Session, user, args: dict) -> dict:
    month = args.get("month")
    summary = finance_service.summary(db, user.id, month)
    budgets = finance_service.list_budgets(db, user.id, month)
    return {
        "month": summary["month"], "income": summary["income"], "expense": summary["expense"],
        "balance": summary["balance"], "study_expense": summary["study_expense"],
        "study_ratio": summary["study_ratio"], "categories": summary["categories"][:6],
        "budgets": [{"category": b["category_label"], "limit": b["limit_amount"],
                     "used": b["used"], "usage_rate": b["usage_rate"]} for b in budgets],
    }


# ═══════════════ 健康 ═══════════════
@tool("log_health_record", "记录今日健康数据（睡眠/运动/久坐/体重/饮水），同日多次提交自动累加",
      _obj({"sleep_minutes": _INT, "exercise_minutes": _INT, "sedentary_minutes": _INT,
           "weight": _NUM, "water_ml": _INT, "note": _STR}))
def log_health_record(db: Session, user, args: dict) -> dict:
    clean = {k: v for k, v in args.items() if v is not None}
    if not clean:
        return {"ok": False, "error": "请至少提供一个健康字段（sleep_minutes/exercise_minutes/water_ml 等）"}
    payload = HealthRecordIn(**clean)
    record = health_service.upsert_record(db, user.id, payload)
    dashboard_service.invalidate(user.id)
    return {"ok": True, "record": record.to_dict()}


@tool("get_health_report", "获取健康报告：日均睡眠、运动达标率、久坐状态、体重变化与建议",
      _obj({"days": {**_INT, "description": "统计天数，默认 7"}}))
def get_health_report(db: Session, user, args: dict) -> dict:
    data = health_service.report(db, user.id, days=int(args.get("days") or 7))
    return {k: data[k] for k in ("avg_sleep_hours", "avg_exercise_minutes", "week_exercise_minutes",
                                 "exercise_goal_rate", "weight_change", "sedentary", "tips")}


@tool("take_sedentary_break", "记录一次起身活动，重置久坐计时", _obj({}))
def take_sedentary_break(db: Session, user, args: dict) -> dict:
    result = health_service.take_break(db, user.id)
    dashboard_service.invalidate(user.id)
    return {"ok": True, **result}


# ═══════════════ 辅助 ═══════════════
def _parse_due(value: Any, day_only: bool = False) -> datetime | date | None:
    if not value:
        return None
    if isinstance(value, (datetime, date)):
        return value
    text = str(value).strip().replace("/", "-")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed.date() if day_only else parsed
        except ValueError:
            continue
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d")
        if day_only:
            return parsed.date()
        return parsed.replace(hour=23, minute=59)
    except ValueError:
        return None


async def execute(db: Session, user, name: str, arguments: dict) -> dict:
    """执行工具：统一异常包装，保证 Function Call 循环不中断。"""
    handler = HANDLERS.get(name)
    if not handler:
        return {"ok": False, "error": f"未知工具 {name}，可用工具：{', '.join(tool_names())}"}
    try:
        result = handler(db, user, arguments or {})
        if hasattr(result, "__await__"):
            result = await result
        return result if isinstance(result, dict) else {"ok": True, "result": result}
    except AppError as exc:
        db.rollback()
        return {"ok": False, "error": exc.message}
    except Exception as exc:                     # pragma: no cover
        logger.exception("工具 %s 执行失败", name)
        db.rollback()
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
