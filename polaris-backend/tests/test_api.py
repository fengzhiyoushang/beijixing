"""端到端冒烟测试：覆盖 10 张核心表与全部模块接口。

运行： .venv\\Scripts\\python -m pytest tests -q
说明： 使用独立 SQLite 文件 + 关闭 Redis + 演示模式 AI，无需任何外部依赖。
"""
from __future__ import annotations

import base64
import os
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_DB = ROOT / "data" / "test_polaris.db"
os.environ["DB_BACKEND"] = "sqlite"
os.environ["SQLITE_PATH"] = str(TEST_DB)
os.environ["REDIS_ENABLED"] = "false"
os.environ["DEEPSEEK_API_KEY"] = ""
os.environ["DEBUG"] = "false"

if TEST_DB.exists():                             # 每次跑测试用干净库
    TEST_DB.unlink()

from fastapi.testclient import TestClient          # noqa: E402

from app.core.database import init_db              # noqa: E402
from app.main import app                           # noqa: E402

init_db()      # TestClient 未作为上下文管理器时不触发 lifespan，这里显式建表

client = TestClient(app)

TODAY = date.today()
UNIQUE = str(int(time.time()))
USERNAME = f"tester_{UNIQUE}"
PASSWORD = "test123456"
TOKEN: str = ""
H: dict = {}


def day(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def stamp(offset_days: int, hour: int = 10, minute: int = 0) -> str:
    base = datetime.combine(TODAY + timedelta(days=offset_days), datetime.min.time())
    return (base + timedelta(hours=hour, minutes=minute)).strftime("%Y-%m-%dT%H:%M:%S")


def test_full_flow() -> None:
    global TOKEN, H

    # ── 健康检查 ──
    r = client.get("/health")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] in {"ok", "degraded"}
    print("health:", body["database"]["engine"], body["cache"]["mode"], body["ai"]["mode"])

    # ── ① 用户认证 ──
    r = client.post("/api/v1/auth/register", json={
        "username": USERNAME, "password": PASSWORD, "nickname": "测试同学"})
    assert r.status_code == 200, r.text
    TOKEN = r.json()["access_token"]
    H = {"Authorization": f"Bearer {TOKEN}"}
    assert client.post("/api/v1/auth/login",
                       json={"username": USERNAME, "password": PASSWORD}).status_code == 200
    assert client.post("/api/v1/auth/login",
                       json={"username": USERNAME, "password": "wrong"}).status_code == 401
    me = client.get("/api/v1/auth/me", headers=H).json()
    assert me["username"] == USERNAME
    client.put("/api/v1/auth/me/config", json={"config": {"school": "华中科技大学"}, "merge": True},
               headers=H)
    wx = client.post("/api/v1/auth/wx-login", json={"code": f"code_{UNIQUE}"})
    assert wx.status_code == 200 and wx.json()["user"]["wx_bound"] is True
    print("auth ok:", me["nickname"])

    # ── ② 课程表 + 学期 ──
    sem = client.post("/api/v1/courses/semesters", headers=H, json={
        "name": "测试学期", "total_weeks": 20, "is_current": True,
        "start_date": day(-42)}).json()
    assert sem["is_current"] is True and sem["current_week"] >= 6
    course_body = {
        "name": "数据结构与算法", "teacher": "王教授", "location": "东一舍 A302", "credit": 4,
        "semester_id": sem["id"],
        "schedules": [{"weekday": 1, "start_section": 1, "end_section": 2,
                       "start_time": "08:00", "end_time": "09:40", "weeks": "1-16",
                       "week_type": "全周", "location": "东一舍 A302"}],
    }
    course = client.post("/api/v1/courses", headers=H, json=course_body)
    assert course.status_code == 200, course.text
    course_id = course.json()["id"]

    # 冲突检测：同一天时间重叠
    conflict = client.post("/api/v1/courses", headers=H, json={
        **course_body, "name": "操作系统原理",
        "schedules": [{**course_body["schedules"][0], "start_time": "08:30", "end_time": "10:00"}]})
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["detail"]["conflicts"], "应返回冲突明细"
    forced = client.post("/api/v1/courses?force=true", headers=H, json={
        **course_body, "name": "操作系统原理（强制）"})
    assert forced.status_code == 200
    print("course conflict detected:", conflict.json()["message"])

    imported = client.post("/api/v1/courses/import", headers=H, json={
        "semester_id": sem["id"], "courses": [
            {"name": "线性代数", "teacher": "李老师", "credit": 3,
             "schedules": [{"weekday": 2, "start_time": "14:00", "end_time": "15:40",
                            "weeks": "1-16", "start_section": 5, "end_section": 6}]},
            {"name": "大学英语", "teacher": "周老师", "credit": 2,
             "schedules": [{"weekday": 5, "start_time": "10:00", "end_time": "11:40",
                            "weeks": "1-16", "start_section": 3, "end_section": 4}]},
        ]}).json()
    assert imported["created"] == 2, imported
    week = client.get("/api/v1/courses/week", headers=H).json()
    assert week["total_classes"] >= 3
    assert client.get("/api/v1/courses/today", headers=H).status_code == 200
    assert client.get(f"/api/v1/courses/{course_id}", headers=H).json()["name"] == "数据结构与算法"
    client.put(f"/api/v1/courses/{course_id}", headers=H, json={"teacher": "王建民"})
    print("courses ok:", week["total_classes"], "slots in week", week["week"])

    # ── ③ DDL 任务 + 子任务 ──
    task = client.post("/api/v1/tasks", headers=H, json={
        "title": "操作系统实验报告", "category": "课程", "priority": "high",
        "due_at": stamp(2, 22), "course_id": course_id,
        "subtasks": [{"title": "写代码"}, {"title": "写报告"}]}).json()
    assert task["subtask_total"] == 2 and task["remaining_seconds"] > 0
    sub = client.post(f"/api/v1/tasks/{task['id']}/subtasks", headers=H,
                      json={"title": "提交"}).json()
    client.put(f"/api/v1/tasks/subtasks/{sub['id']}", headers=H, json={"is_done": True})
    client.post("/api/v1/tasks", headers=H, json={
        "title": "已逾期任务", "priority": "medium", "due_at": stamp(-1, 20)})
    stats = client.get("/api/v1/tasks/stats", headers=H).json()
    assert stats["pending"] >= 2 and stats["overdue"] >= 1 and len(stats["trend"]) == 7
    assert client.get("/api/v1/tasks/upcoming?within_days=7", headers=H).status_code == 200
    assert client.get("/api/v1/tasks/categories", headers=H).json()["items"]
    done = client.post(f"/api/v1/tasks/{task['id']}/complete", headers=H).json()
    assert done["status"] == "done" and done["subtask_done"] == 3
    client.post(f"/api/v1/tasks/{task['id']}/uncomplete", headers=H)
    print("tasks ok: pending", stats["pending"], "overdue", stats["overdue"],
          "completion", stats["completion_rate"])

    # ── ④⑤ 空教室 ──
    room = client.post("/api/v1/classroom/classrooms", headers=H, json={
        "building": "东一舍", "room_no": "A302", "capacity": 120, "seats": 118}).json()
    assert room["name"] == "东一舍 A302"
    sample_day = TODAY - timedelta(days=7)
    # 同一天同一时段多次采样：4 次空闲 + 1 次占用
    for minute in (0, 5, 10, 15):
        client.post("/api/v1/classroom/status", headers=H, json={
            "building": "东一舍", "room_no": "A302", "status": "free", "source": "manual",
            "confidence": 1.0,
            "recorded_at": f"{sample_day.isoformat()}T10:{minute:02d}:00"})
    client.post("/api/v1/classroom/status", headers=H, json={
        "building": "东一舍", "room_no": "A302", "status": "busy", "source": "ai_vision",
        "confidence": 0.8, "recorded_at": f"{sample_day.isoformat()}T10:30:00"})
    rate = client.get("/api/v1/classroom/free-rate?building=东一舍&room_no=A302", headers=H).json()
    assert rate["samples"] >= 5 and "matrix" in rate
    weekday_of_sample = sample_day.isoweekday()
    pred = client.get(f"/api/v1/classroom/predict?weekday={weekday_of_sample}&hour=10",
                      headers=H).json()
    assert pred["results"], f"应预测出教室：{pred}"
    assert 0 <= pred["results"][0]["confidence"] <= 100
    assert client.get("/api/v1/classroom/buildings", headers=H).status_code == 200
    assert client.get("/api/v1/classroom/overview", headers=H).status_code == 200
    assert client.get("/api/v1/classroom/status/recent", headers=H).status_code == 200
    vision = client.post("/api/v1/classroom/recognize", headers=H, json={
        "building": "东一舍", "room_no": "A302",
        "image_base64": base64.b64encode(b"fake-image-bytes" * 8).decode(),
        "save_log": True}).json()
    assert vision["recognition"]["status"] in {"free", "busy", "unknown"} and vision["saved"]
    print("classroom ok: samples", rate["samples"], "predict",
          pred["results"][0]["name"], pred["results"][0]["confidence"],
          "| vision", vision["recognition"]["status"], vision["mode"])

    # ── ⑥ 学习记录 ──
    client.post("/api/v1/study/records", headers=H, json={
        "subject": "数学", "minutes": 120, "content": "强化课 + 真题", "mood": 5,
        "focus_score": 88, "date": day(-1)})
    client.post("/api/v1/study/records", headers=H, json={
        "subject": "408", "minutes": 90, "date": day(-2)})
    mock = client.post("/api/v1/study/mock-scores", headers=H, json={
        "subject": "数学", "mock_name": "模拟卷（三）", "score": 96, "full_score": 150,
        "date": day(-1)}).json()
    assert mock["mock_rate"] == 0.64
    study = client.get("/api/v1/study/stats?days=30", headers=H).json()
    assert study["total_minutes"] >= 210 and study["by_subject"]
    assert study["streak_days"] >= 1
    assert client.get("/api/v1/study/progress", headers=H).status_code == 200
    assert client.get("/api/v1/study/mock-scores", headers=H).json()["total"] >= 1
    print("study ok: minutes", study["total_minutes"], "da", study["active_days"],
          "subjects", len(study["by_subject"]), "streak", study["streak_days"])

    # ── ⑦ 考研规划 ──
    target = client.put("/api/v1/kaoyan/target", headers=H, json={
        "school": "华中科技大学", "major": "计算机科学与技术（学硕）", "degree_type": "学硕",
        "exam_date": day(95),
        "subject_scores": [
            {"subject": "政治", "target": 75, "current": 58, "max": 100, "line": 60},
            {"subject": "英语一", "target": 80, "current": 62, "max": 100, "line": 60},
            {"subject": "数学一", "target": 130, "current": 96, "max": 150, "line": 90},
            {"subject": "408 计算机", "target": 135, "current": 73, "max": 150, "line": 90},
        ]}).json()
    assert target["total_target"] == 420 and target["total_current"] == 289
    gap = client.get("/api/v1/kaoyan/gap-analysis", headers=H).json()
    assert gap["total_gap"] == 131 and gap["focus_subjects"] and gap["days_left"] == 95
    plan = client.post("/api/v1/kaoyan/plan/generate", headers=H, json={
        "total_weeks": 16, "daily_minutes": 300, "use_ai": True}).json()
    assert plan["phases"] >= 2 and plan["daily_tasks"] >= 1
    assert client.get("/api/v1/kaoyan/plans", headers=H).json()["phases"]
    tasks = client.get("/api/v1/kaoyan/plan/tasks", headers=H).json()["items"]
    assert tasks, "应生成每日任务"
    client.put(f"/api/v1/kaoyan/plan/tasks/{tasks[0]['id']}", headers=H, json={"is_done": True})
    score = client.post("/api/v1/kaoyan/scores", headers=H, json={
        "subject": "数学一", "current": 108, "add_study_record": True, "minutes": 60}).json()
    assert score["gap_analysis"]["total_current"] == 301
    assert client.get("/api/v1/kaoyan/progress", headers=H).json()["has_target"] is True
    print("kaoyan ok: plan source", plan["source"], "phases", plan["phases"],
          "daily", plan["daily_tasks"], "| gap", gap["total_gap"], "->",
          score["gap_analysis"]["total_gap"])

    # ── ⑧ 知识库（含向量化与 RAG） ──
    folder = client.post("/api/v1/knowledge/folders", headers=H, json={"name": "考研 408"}).json()
    doc = client.post("/api/v1/knowledge/docs", headers=H, json={
        "title": "进程调度算法对比笔记",
        "content": ("# 进程调度\n\n时间片轮转 RR 按固定时间片轮流执行就绪队列中的进程，"
                    "强调公平性与响应时间，适合分时系统。\n\n"
                    "优先级调度按进程优先级高低分配 CPU，可抢占或非抢占，实时系统常用。\n\n"
                    "多级反馈队列把两者结合：同优先级内部采用 RR。"),
        "folder_id": folder["id"], "tags": ["408-操作系统"], "auto_vectorize": True}).json()
    assert doc["vector_status"] == "done" and doc["vector_count"] >= 1
    detail = client.get(f"/api/v1/knowledge/docs/{doc['id']}", headers=H).json()
    assert "时间片轮转" in detail["content"]
    search = client.post("/api/v1/knowledge/search", headers=H,
                         json={"keyword": "时间片轮转", "mode": "hybrid"}).json()
    assert search["chunks"], "混合检索应命中切片"
    qa = client.post("/api/v1/knowledge/qa", headers=H,
                     json={"question": "时间片轮转和优先级调度有什么区别？", "mode": "auto"}).json()
    assert qa["answer"] and qa["references"], "应返回答案与引用"
    kb = client.get("/api/v1/knowledge/stats", headers=H).json()
    assert kb["doc_count"] >= 1 and kb["chunk_count"] >= 1 and kb["coverage"] > 0
    assert client.get(f"/api/v1/knowledge/docs/{doc['id']}/chunks", headers=H).json()["total"] >= 1
    print("knowledge ok: chunks", kb["chunk_count"], "coverage", kb["coverage"],
          "| qa mode", qa["mode"], "refs", len(qa["references"]))

    # ── ⑨ 财务 ──
    month = TODAY.strftime("%Y-%m")
    client.post("/api/v1/finance/records", headers=H, json={
        "type": "expense", "category": "学习投入", "amount": 320, "is_study": True,
        "note": "考研数学网课", "occurred_at": stamp(0, 9, 30)})
    client.post("/api/v1/finance/records", headers=H, json={
        "type": "expense", "category": "餐饮", "amount": 85, "occurred_at": stamp(0, 12)})
    client.post("/api/v1/finance/records", headers=H, json={
        "type": "income", "category": "生活费", "amount": 2500, "occurred_at": stamp(0, 8)})
    summary = client.get(f"/api/v1/finance/summary?month={month}", headers=H).json()
    assert summary["expense"] == 405 and summary["study_expense"] == 320
    assert summary["balance"] == 2095 and summary["study_ratio"] > 0.7
    budget = client.post("/api/v1/finance/budgets", headers=H, json={
        "month": month, "category": "*", "limit_amount": 2200}).json()
    assert budget["usage_rate"] > 0 and budget["remaining"] > 0
    assert client.get("/api/v1/finance/trend?months=6", headers=H).json()["items"]
    study_ana = client.get("/api/v1/finance/study-analysis", headers=H).json()
    assert study_ana["total_study_expense"] == 320
    print("finance ok: expense", summary["expense"], "balance", summary["balance"],
          "study ratio", summary["study_ratio"], "budget used", budget["usage_rate"])

    # ── ⑩ 健康 ──
    client.post("/api/v1/health/records", headers=H, json={
        "date": day(-1), "sleep_minutes": 435, "exercise_minutes": 45, "weight": 68.4,
        "water_ml": 1500, "bed_time": "23:48", "wake_time": "07:00"})
    client.post("/api/v1/health/records", headers=H, json={
        "date": day(-1), "water_ml": 500, "exercise_minutes": 15})   # 累加型字段
    report = client.get("/api/v1/health/report?days=7", headers=H).json()
    assert report["avg_sleep_hours"] > 0 and report["tips"] and report["week_exercise_minutes"] == 60
    record = client.get("/api/v1/health/records?days=7", headers=H).json()["items"][0]
    assert record["water_ml"] == 2000 and record["exercise_minutes"] == 60, record
    client.put("/api/v1/health/settings", headers=H, json={"sedentary_interval_min": 30,
                                                           "target_water_ml": 2200})
    hb = client.post("/api/v1/health/sedentary/heartbeat", headers=H,
                     json={"spent_minutes": 30}).json()
    assert "should_break" in hb and hb["interval_min"] == 30
    brk = client.post("/api/v1/health/sedentary/break", headers=H,
                      json={"note": "楼梯 3 层"}).json()
    assert brk["minutes_since_break"] <= 1
    print("health ok: sleep", report["avg_sleep_hours"], "exercise",
          report["week_exercise_minutes"], "tips", len(report["tips"]),
          "| sedentary", hb["minutes_since_break"], "->", brk["minutes_since_break"])

    # ── ⑪ 系统管理 ──
    client.post("/api/v1/system/configs", headers=H, json={
        "key": "app.theme", "value": {"mode": "dark", "accent": "#4ade80"}, "group": "ui"})
    configs = client.get("/api/v1/system/configs", headers=H).json()
    assert configs["total"] >= 1
    runtime = client.get("/api/v1/system/runtime", headers=H).json()
    assert runtime["database"]["engine"] in {"sqlite", "mysql"} and runtime["ai"]["mode"] == "mock"
    tables = client.get("/api/v1/system/tables", headers=H).json()["items"]
    assert len(tables) >= 23, len(tables)
    backup = client.post("/api/v1/system/backups", headers=H, json={"scope": "user"}).json()
    assert backup["size_bytes"] > 0 and backup["row_counts"]["ddl_tasks"] >= 2
    assert client.get("/api/v1/system/backups", headers=H).json()["total"] >= 1
    assert client.post(f"/api/v1/system/backups/{backup['id']}/restore",
                       headers=H).status_code == 400      # 未确认时应拒绝
    restored = client.post(f"/api/v1/system/backups/{backup['id']}/restore?confirm=true",
                           headers=H).json()
    assert restored["tables"] >= 5
    print("system ok: tables", len(tables), "backup rows", backup["row_counts"]["ddl_tasks"],
          "| restored tables", restored["tables"])

    # ── ⑫ AI（工具 + 对话 + 会话 + SSE） ──
    status = client.get("/api/v1/ai/status", headers=H).json()
    assert status["ai"]["mode"] in {"live", "mock"}
    tool_list = client.get("/api/v1/ai/tools", headers=H).json()
    assert tool_list["total"] >= 15, tool_list["total"]
    names = {t["name"] for t in tool_list["items"]}
    for expected in ("query_schedule", "add_ddl_task", "get_study_progress", "classroom_predict",
                     "get_kaoyan_gap", "search_knowledge", "rag_answer", "add_finance_record",
                     "get_finance_summary", "log_health_record", "get_health_report"):
        assert expected in names, f"缺少工具 {expected}"

    called = client.post("/api/v1/ai/tools/call", headers=H, json={
        "name": "get_dashboard_summary", "arguments": {"days": 7}}).json()
    assert "tasks" in called and "study" in called
    added = client.post("/api/v1/ai/tools/call", headers=H, json={
        "name": "add_ddl_task", "arguments": {"title": "AI 新建的任务", "priority": "high",
                                              "due_at": f"{day(3)} 23:00"}}).json()
    assert added["ok"] is True and added["task"]["title"] == "AI 新建的任务"
    assert client.post("/api/v1/ai/tools/call", headers=H, json={
        "name": "get_study_progress", "arguments": {}}).json()["total_hours"] > 0
    assert client.post("/api/v1/ai/tools/call", headers=H, json={
        "name": "classroom_predict", "arguments": {"limit": 3}}).json()["results"]
    assert client.post("/api/v1/ai/tools/call", headers=H, json={
        "name": "not_exists", "arguments": {}}).json()["ok"] is False

    chat = client.post("/api/v1/ai/chat", headers=H, json={"message": "今天有什么课？"}).json()
    assert chat["session_id"] and chat["reply"]
    assert client.get("/api/v1/ai/sessions", headers=H).json()["total"] >= 1
    detail = client.get(f"/api/v1/ai/sessions/{chat['session_id']}", headers=H).json()
    assert len(detail["messages"]) >= 2
    with client.stream("POST", "/api/v1/ai/chat/stream", headers=H,
                       json={"message": "帮我看看学习进度"}) as resp:
        events = []
        for line in resp.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if "done" in events or "error" in events:
                break
    assert "meta" in events, events
    print("ai ok: tools", tool_list["total"], "traces", len(chat["tool_traces"]),
          "| sse", events[:5])

    # ── ⑬ 总览仪表盘 + 微信订阅消息 ──
    summary = client.get("/api/v1/dashboard/summary?days=7", headers=H).json()
    assert "courses_today" in summary and "tasks" in summary and "alerts" in summary
    assert summary["study"]["total_hours"] > 0
    assert client.get("/api/v1/dashboard/alerts", headers=H).json()["total"] >= 1
    assert client.post("/api/v1/dashboard/cache/clear", headers=H).json()["cleared"] is True

    wx_status = client.get("/api/v1/wechat/status", headers=H).json()
    assert wx_status["mode"] == "mock" and "templates" in wx_status
    quota0 = client.get("/api/v1/wechat/quota", headers=H).json()
    assert quota0["total_remaining"] == 0
    granted = client.post("/api/v1/wechat/subscribe/quota", headers=H,
                          json={"kind": "ddl", "times": 2}).json()
    assert granted["granted"] is True and granted["quota"]["remaining"] == 2
    client.post("/api/v1/auth/wx/bind", headers=H, json={"code": f"bind_{UNIQUE}"})
    pushed = client.post("/api/v1/wechat/push/test", headers=H,
                         json={"kind": "ddl", "title": "测试：实验报告", "due_at": stamp(0, 22)}).json()
    assert pushed["status"] == "success", pushed
    quota1 = client.get("/api/v1/wechat/quota", headers=H).json()
    assert quota1["total_remaining"] == 1, quota1
    scan = client.post("/api/v1/wechat/push/scan", headers=H).json()
    assert "ddl" in scan and "class" in scan
    assert client.get("/api/v1/wechat/push-logs", headers=H).json()["total"] >= 1
    print("dashboard+wechat ok: 总览小时", summary["study"]["total_hours"],
          "| 配额", quota0["total_remaining"], "→", quota1["total_remaining"],
          "| 扫描 DDL 候选", scan["ddl"]["candidates"])

    # ── 收尾：权限隔离 ──
    other = client.post("/api/v1/auth/register", json={
        "username": f"other_{UNIQUE}", "password": PASSWORD}).json()
    other_h = {"Authorization": f"Bearer {other['access_token']}"}
    assert client.get(f"/api/v1/courses/{course_id}", headers=other_h).status_code == 404
    assert client.get("/api/v1/tasks/stats", headers=other_h).json()["total"] == 0
    assert client.get("/api/v1/courses/week", headers={}).status_code == 401
    print("isolation ok: 跨用户隔离 + 未认证 401")

    print("\n✅ 全部模块通过：认证/课程/任务/教室/学习/考研/知识库/财务/健康/系统/AI")
