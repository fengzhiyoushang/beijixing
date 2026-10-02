"""演示数据脚本：一键生成可直接体验的全量数据。

    python scripts/seed_demo.py            # 追加（若已存在 admin 则跳过）
    python scripts/seed_demo.py --reset    # 清空演示用户数据后重建

演示账号：admin / admin123
"""
from __future__ import annotations

import argparse
import asyncio
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):             # pragma: no cover
    pass

from app.ai import rag                          # noqa: E402
from app.core.database import init_db, session_scope  # noqa: E402
from app.core.security import hash_password      # noqa: E402
from app.models import (Classroom, ClassroomStatusLog, Course, CourseSchedule, DdlTask,  # noqa: E402
                        FinanceBudget, FinanceRecord, HealthRecord, HealthSetting,
                        KaoyanPlanPhase, KaoyanPlanTask, KaoyanTarget, KnowledgeDoc,
                        KnowledgeFolder, Semester, StudyRecord, SubTask, SystemConfig, User)

RNG = random.Random(20261014)
DEMO_USER = "admin"
DEMO_PASSWORD = "admin123"

COURSE_SEED = [
    ("数据结构与算法", "王建民", "东一舍 A302", 4.0, "#60a5fa", [(1, "08:00", "09:40", "1-16"), (4, "14:00", "15:40", "5-15")]),
    ("操作系统原理", "张海鹏", "东一舍 A305", 3.5, "#4ade80", [(3, "08:00", "09:40", "2-17"), (5, "08:00", "09:40", "2-17")]),
    ("计算机网络", "陈立群", "网楼 B203", 3.0, "#f87171", [(3, "16:00", "17:40", "1-16双")]),
    ("线性代数", "李晓芸", "东二舍 401", 3.0, "#facc15", [(2, "14:00", "15:40", "1-16"), (4, "10:00", "11:40", "1-16")]),
    ("大学英语（考研方向）", "周敏", "外语楼 305", 2.0, "#c084fc", [(5, "10:00", "11:40", "1-16")]),
]

CLASSROOMS = [
    ("东一舍", "A302", 120, 118, "普通教室"),
    ("东一舍", "A305", 120, 118, "普通教室"),
    ("网楼", "B101", 90, 88, "机房"),
    ("图书馆", "4F北区", 200, 200, "自习室"),
    ("西五舍", "研讨间2", 24, 24, "研讨间"),
]

KAOYAN_SUBJECTS = [
    {"subject": "政治", "target": 75, "current": 58, "max": 100, "line": 60, "note": "马原薄弱"},
    {"subject": "英语一", "target": 80, "current": 62, "max": 100, "line": 60, "note": "阅读稳定"},
    {"subject": "数学一", "target": 130, "current": 96, "max": 150, "line": 90, "note": "线代提升明显"},
    {"subject": "408 计算机", "target": 135, "current": 73, "max": 150, "line": 90, "note": "大题步骤分丢失"},
]

KNOWLEDGE_DOCS = [
    ("408-操作系统", "进程调度算法对比笔记",
     "# 进程调度算法对比\n\n## 时间片轮转 RR\n按固定时间片轮流执行就绪队列进程，强调公平与响应时间，适合分时系统。\n\n"
     "## 优先级调度\n按优先级分配 CPU，可抢占或非抢占，实时系统常用；同优先级内部可采用 RR，多级反馈队列即此思路。\n\n"
     "## 关键区别\n1. RR 关注公平，优先级关注重要性；\n2. RR 时间片过小导致上下文切换开销上升；\n3. 优先级调度可能饥饿，可用老化解决。"),
    ("数学强化", "数学一高频错题归档",
     "# 数学一错题归档（第 3 轮）\n\n## 高数\n- 变限积分求导忽略链式法则；\n- 二重积分换序时积分限写错。\n\n"
     "## 线代\n- 特征值重根时忽略广义特征向量；\n- 相似对角化条件判断失误。\n\n## 概率\n- 全概率与贝叶斯公式混用。"),
    ("408-网络", "运输层要点速记",
     "# 运输层\n\n## TCP 可靠传输\n序号确认、超时重传、快速重传、滑动窗口。\n\n## 拥塞控制\n慢开始、拥塞避免、快重传、快恢复。\n\n"
     "## UDP\n无连接、首部 8 字节、适合实时音视频。"),
    ("英语长难句", "英语一长难句拆解 20 例",
     "# 长难句拆解\n\n## 例 1\n*What is harder to establish is whether the productivity revolution is for real.*\n"
     "主语从句 + 表语从句；译：更难确定的是这场生产率革命是否真实存在。\n\n## 例 2\n同位语从句常由 that 引导，注意与定语从句区分。"),
    ("政治", "毛概时间线速记",
     "# 毛概时间线\n- 1921 建党；- 1927 井冈山；- 1935 遵义会议；- 1945 七大；- 1949 建国；- 1978 十一届三中全会。"),
]


# ══════════════ 各模块数据 ══════════════
def _seed_user(db) -> User:
    user = db.query(User).filter(User.username == DEMO_USER).first()
    if user:
        return user
    user = User(
        username=DEMO_USER, password_hash=hash_password(DEMO_PASSWORD),
        nickname="北极星同学", email="polaris@example.com", role="admin",
        wx_openid="dev_demo_openid_0001", wx_nickname="小程序同学",
        config={"theme": "dark", "accent": "#4ade80", "school": "华中科技大学",
                "role": "23 级计算机 · 考研备战中", "weather_city": "武汉", "semester_weeks": 20},
    )
    db.add(user)
    db.flush()
    return user


def _seed_courses(db, user) -> Semester:
    today = date.today()
    start = today - timedelta(weeks=6)
    semester = Semester(user_id=user.id, name=f"{today.year}-{today.year + 1} 学年第一学期",
                        start_date=start, end_date=start + timedelta(weeks=20), total_weeks=20,
                        is_current=True)
    db.add(semester)
    db.flush()
    for name, teacher, location, credit, color, slots in COURSE_SEED:
        course = Course(user_id=user.id, semester_id=semester.id, name=name, teacher=teacher,
                        location=location, credit=credit, color=color, course_type="必修")
        db.add(course)
        db.flush()
        for weekday, st, et, weeks in slots:
            db.add(CourseSchedule(
                course_id=course.id, weekday=weekday, start_time=st, end_time=et, weeks=weeks,
                start_section=1 if st < "12:00" else 5, end_section=2 if st < "12:00" else 6,
                location=location, week_type="双周" if "双" in weeks else "全周",
            ))
    return semester


def _seed_tasks(db, user, courses) -> None:
    now = datetime.now()
    rows = [
        ("操作系统进程调度实验报告", "课程", "high", now + timedelta(hours=4), "完成 RR 与优先级调度对比实验"),
        ("数学模拟卷（三）订正归档", "考研", "high", now + timedelta(hours=7), "错题写入知识库"),
        ("计算机网络实验预习笔记上传知识库", "知识整理", "medium", now + timedelta(hours=2), None),
        ("考研报名网上确认材料准备", "考研", "high", now + timedelta(days=11), "学信网确认"),
        ("数据结构结课大作业开题", "课程", "medium", now + timedelta(days=14), "选定题目"),
        ("六级单词冲刺计划第 3 阶段", "考研", "medium", now + timedelta(days=30), None),
        ("整理 10 月错题本电子档", "知识整理", "medium", now - timedelta(days=1), "已逾期，尽快补"),
        ("图书馆书籍归还", "生活", "low", now - timedelta(days=3), None),
    ]
    for i, (title, category, priority, due, desc) in enumerate(rows):
        task = DdlTask(user_id=user.id, title=title, category=category, priority=priority,
                       due_at=due, description=desc, source="web",
                       course_id=courses[0].id if category == "课程" else None,
                       estimate_minutes=RNG.choice([30, 60, 90, 120]),
                       tags=[category])
        if i in (7,):
            task.status = "done"
            task.completed_at = due + timedelta(hours=2)
        db.add(task)
        db.flush()
        if category in {"课程", "考研"}:
            for j, sub in enumerate(["资料收集", "主体完成", "复核提交"]):
                db.add(SubTask(task_id=task.id, title=sub, sort_order=j,
                               is_done=task.status == "done" or j == 0))


def _seed_classrooms(db, user) -> None:
    for building, room_no, capacity, seats, room_type in CLASSROOMS:
        room = Classroom(building=building, room_no=room_no, capacity=capacity, seats=seats,
                         room_type=room_type, floor=int(room_no[-1]) if room_no[-1].isdigit() else 1,
                         open_time="07:00", close_time="22:30")
        db.add(room)
        db.flush()
        # 近 4 周、每周同一 weekday×hour 采样
        for weeks_ago in range(1, 5):
            for weekday in range(1, 8):
                for hour in (8, 10, 14, 16, 19, 20):
                    base_day = (date.today() - timedelta(days=date.today().isoweekday() - weekday)
                                - timedelta(weeks=weeks_ago))
                    recorded = datetime(base_day.year, base_day.month, base_day.day, hour,
                                        RNG.randint(0, 59))
                    busy_hours = {8, 10, 14}
                    free_bias = 0.25 if hour in busy_hours else 0.8
                    if room_type == "自习室":
                        free_bias += 0.1
                    status = "free" if RNG.random() < free_bias else "busy"
                    occupied = 0 if status == "free" else RNG.randint(5, max(6, seats))
                    db.add(ClassroomStatusLog(
                        classroom_id=room.id, user_id=user.id, building=building, room_no=room_no,
                        status=status, occupied_seats=occupied,
                        source=RNG.choice(["miniapp", "manual", "ai_vision"]),
                        confidence=round(RNG.uniform(0.75, 0.98), 2),
                        recorded_at=recorded, weekday=weekday, hour=hour,
                    ))


def _seed_study(db, user) -> None:
    subjects = ["数学", "英语", "408", "政治", "综合"]
    activities = ["真题", "强化课", "错题订正", "背诵", "章节练习"]
    for i in range(21, -1, -1):
        day = date.today() - timedelta(days=i)
        if i == 5:                                # 制造一个断点
            continue
        for _ in range(RNG.randint(1, 3)):
            minutes = RNG.choice([45, 60, 75, 90, 120])
            subject = RNG.choice(subjects)
            activity = RNG.choice(activities)
            db.add(StudyRecord(
                user_id=user.id, date=day, subject=subject, minutes=minutes,
                content=f"{subject} {activity}",
                mood=RNG.randint(3, 5), focus_score=RNG.randint(60, 95),
            ))
    for name, subject, score, full in [("数学模拟卷（三）", "数学", 96, 150),
                                       ("英语真题 2020", "英语", 62, 100),
                                       ("408 真题 2021", "408", 73, 150)]:
        db.add(StudyRecord(user_id=user.id, date=date.today() - timedelta(days=RNG.randint(1, 10)),
                           subject=subject, minutes=0, content=f"模考：{name}", mock_name=name,
                           mock_score=score, mock_full_score=full, focus_score=RNG.randint(70, 92)))


def _seed_kaoyan(db, user) -> None:
    exam = date(date.today().year + (1 if date.today().month > 10 else 0), 12, 26)
    target = KaoyanTarget(
        user_id=user.id, school="华中科技大学", major="计算机科学与技术（学硕）",
        degree_type="学硕", exam_date=exam, subject_scores=KAOYAN_SUBJECTS,
        total_target=sum(s["target"] for s in KAOYAN_SUBJECTS),
        total_current=sum(s["current"] for s in KAOYAN_SUBJECTS),
        note="目标：408 与数学拉分",
    )
    db.add(target)
    db.flush()

    phases = [
        ("基础阶段", 12, "教材通读 + 基础题全覆盖，建立知识框架与笔记体系", 100),
        ("强化阶段", 10, "专题突破 + 真题一轮，错题归档进入知识库做 RAG 复盘", 74),
        ("冲刺阶段", 6, "模拟卷限时训练 + 查漏补缺 + 政治与英语背诵冲刺", 0),
    ]
    start = date.today() - timedelta(weeks=16)
    first_phase = None
    for i, (name, weeks, focus, progress) in enumerate(phases):
        phase = KaoyanPlanPhase(target_id=target.id, name=name, start_date=start,
                                end_date=start + timedelta(weeks=weeks) - timedelta(days=1),
                                focus=focus, subjects=["数学", "英语", "政治", "408"],
                                progress=progress, sort_order=i, source="ai")
        db.add(phase)
        db.flush()
        if first_phase is None:
            first_phase = phase
        start = phase.end_date + timedelta(days=1)

    daily = [
        ("数学", "880 题 线代章节 12 题订正", 75, True),
        ("408", "操作系统·进程调度 强化课 1.5h", 90, True),
        ("英语", "长难句精析 3 句 + 核心词 60 个", 50, False),
        ("政治", "马原选择题 20 题", 40, False),
        ("整理", "错题归档入知识库（RAG 更新）", 25, False),
    ]
    for i, (subject, title, minutes, done) in enumerate(daily):
        db.add(KaoyanPlanTask(phase_id=first_phase.id, title=title, subject=subject,
                              minutes=minutes, is_done=done, plan_date=date.today()))


def _seed_knowledge(db, user) -> None:
    folders = {}
    for name, icon in [("考研 408", "▣"), ("数学", "∑"), ("英语", "A"), ("政治", "★")]:
        folder = KnowledgeFolder(user_id=user.id, name=name, icon=icon)
        db.add(folder)
        db.flush()
        folders[name] = folder.id

    mapping = {"408-操作系统": "考研 408", "408-网络": "考研 408", "数学强化": "数学",
               "英语长难句": "英语", "政治": "政治"}
    docs = []
    for tag, title, content in KNOWLEDGE_DOCS:
        doc = KnowledgeDoc(user_id=user.id, folder_id=folders.get(mapping.get(tag, ""), None),
                           title=title, content=content, tags=[tag], doc_type="markdown",
                           word_count=len(content), read_count=RNG.randint(3, 22),
                           summary=content[:120])
        db.add(doc)
        db.flush()
        docs.append(doc)
    db.commit()

    async def _index():
        for doc in docs:
            await rag.build_index(db, doc)

    asyncio.run(_index())


def _seed_finance(db, user) -> None:
    month = f"{date.today().year:04d}-{date.today().month:02d}"
    db.add(FinanceBudget(user_id=user.id, month=month, category="*", limit_amount=2200))
    for cat, limit in [("餐饮", 900), ("学习投入", 700), ("娱乐", 200)]:
        db.add(FinanceBudget(user_id=user.id, month=month, category=cat, limit_amount=limit))

    categories = [("餐饮", 20, 60), ("交通", 5, 30), ("日用品", 10, 60), ("娱乐", 20, 80)]
    for month_offset in range(5, -1, -1):
        base = (date.today().replace(day=1) - timedelta(days=month_offset * 30))
        for _ in range(RNG.randint(12, 20)):
            cat, low, high = RNG.choice(categories)
            day = min(RNG.randint(1, 28), 28)
            occurred = datetime(base.year, base.month, day, RNG.randint(8, 21), RNG.randint(0, 59))
            db.add(FinanceRecord(user_id=user.id, type="expense", category=cat,
                                 amount=round(RNG.uniform(low, high), 2), occurred_at=occurred,
                                 note=f"{cat}消费", payment_method=RNG.choice(["微信", "支付宝"])))
        for item, amount in [("考研数学强化班网课", 320), ("408 真题册", 68), ("英语词汇书", 45)]:
            if RNG.random() < 0.8:
                occurred = datetime(base.year, base.month, min(RNG.randint(1, 28), 28), 20, 30)
                db.add(FinanceRecord(user_id=user.id, type="expense", category="学习投入",
                                     amount=amount, occurred_at=occurred, is_study=True,
                                     note=item, payment_method="微信"))
        db.add(FinanceRecord(user_id=user.id, type="income", category="生活费",
                             amount=2500, occurred_at=datetime(base.year, base.month, 1, 9, 0),
                             note="父母生活费", payment_method="银行卡"))
        if RNG.random() < 0.6:
            db.add(FinanceRecord(user_id=user.id, type="income", category="助教补贴",
                                 amount=300, occurred_at=datetime(base.year, base.month, 10, 15, 0),
                                 is_study=False, note="助教岗位", payment_method="银行卡"))


def _seed_health(db, user) -> None:
    db.add(HealthSetting(user_id=user.id, sedentary_enabled=True, sedentary_interval_min=45,
                         quiet_start="12:00", quiet_end="14:00", active_start="08:00",
                         active_end="22:30", target_sleep_minutes=450, target_water_ml=2000,
                         target_exercise_minutes=300, last_heartbeat_at=datetime.now() - timedelta(minutes=52)))
    for i in range(13, -1, -1):
        day = date.today() - timedelta(days=i)
        db.add(HealthRecord(
            user_id=user.id, date=day,
            sleep_minutes=RNG.choice([390, 420, 435, 450, 480]),
            exercise_minutes=RNG.choice([0, 0, 30, 45, 60, 75]),
            sedentary_minutes=RNG.randint(240, 480),
            weight=round(68.5 + RNG.uniform(-0.8, 0.8), 1),
            water_ml=RNG.choice([1200, 1450, 1600, 1800, 2000]),
            steps=RNG.randint(3000, 12000), mood=RNG.randint(3, 5),
            bed_time=RNG.choice(["23:20", "23:48", "00:15"]), wake_time="07:00",
            note=RNG.choice([None, "图书馆自习", "跑步 4km", "晚睡，注意调整"]),
        ))


def _seed_configs(db) -> None:
    for key, value, group, desc in [
        ("app.theme", {"mode": "dark", "accent": "#4ade80"}, "ui", "前端主题配置"),
        ("app.weather_city", {"city": "武汉"}, "ui", "天气城市"),
        ("ai.enabled", {"value": True}, "ai", "是否启用 AI 助手"),
        ("ai.persona", {"tone": "务实鼓励", "language": "zh-CN"}, "ai", "AI 语气"),
        ("reminder.ddl_days", {"value": 3}, "reminder", "DDL 提前提醒天数"),
        ("reminder.sedentary", {"value": True}, "reminder", "久坐提醒开关"),
        ("study.daily_goal_minutes", {"value": 300}, "study", "每日学习目标"),
    ]:
        if not db.query(SystemConfig).filter(SystemConfig.key == key).first():
            db.add(SystemConfig(key=key, value=value, group=group, description=desc))


# ══════════════ 入口 ══════════════
def seed(reset: bool = False) -> dict:
    init_db()
    with session_scope() as db:
        user = db.query(User).filter(User.username == DEMO_USER).first()
        if user and reset:
            print("· 清理旧演示数据…")
            from app.models import KnowledgeChunk

            uid = user.id
            db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id.in_(
                db.query(KnowledgeDoc.id).filter(KnowledgeDoc.user_id == uid)
            )).delete(synchronize_session=False)
            db.query(SubTask).filter(
                SubTask.task_id.in_(db.query(DdlTask.id).filter(DdlTask.user_id == uid))
            ).delete(synchronize_session=False)
            db.query(CourseSchedule).filter(
                CourseSchedule.course_id.in_(db.query(Course.id).filter(Course.user_id == uid))
            ).delete(synchronize_session=False)
            db.query(KaoyanPlanTask).filter(
                KaoyanPlanTask.phase_id.in_(
                    db.query(KaoyanPlanPhase.id).filter(KaoyanPlanPhase.target_id.in_(
                        db.query(KaoyanTarget.id).filter(KaoyanTarget.user_id == uid)))
            )).delete(synchronize_session=False)
            for model in (KaoyanPlanPhase, KaoyanTarget, StudyRecord, KnowledgeDoc,
                          KnowledgeFolder, FinanceRecord, FinanceBudget, HealthRecord,
                          HealthSetting, ClassroomStatusLog, DdlTask, Course, Semester):
                db.query(model).filter(model.user_id == uid).delete(synchronize_session=False)
            db.commit()

        if not user:
            user = _seed_user(db)
            print(f"✓ 演示账号：{DEMO_USER} / {DEMO_PASSWORD}")

        if db.query(Semester).filter(Semester.user_id == user.id).first():
            print("· 已存在学期数据，跳过（使用 --reset 可重建）")
            return {"user_id": user.id, "skipped": True}

        semester = _seed_courses(db, user)
        courses = db.query(Course).filter(Course.user_id == user.id).all()
        _seed_tasks(db, user, courses)
        _seed_classrooms(db, user)
        _seed_study(db, user)
        _seed_kaoyan(db, user)
        _seed_knowledge(db, user)
        _seed_finance(db, user)
        _seed_health(db, user)
        _seed_configs(db)
        db.commit()
        print(f"✓ 演示数据写入完成：学期《{semester.name}》、{len(courses)} 门课程、"
              f"{len(CLASSROOMS)} 间教室、{len(KNOWLEDGE_DOCS)} 篇已向量化文档")
        return {"user_id": user.id, "semester_id": semester.id, "courses": len(courses)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="写入演示数据")
    parser.add_argument("--reset", action="store_true", help="清空演示用户的业务数据后重建")
    arguments = parser.parse_args()
    result = seed(reset=arguments.reset)
    print(result)
