"""首次启动演示数据：admin / admin123，覆盖全部 8 大模块，双端立即可看效果。"""
import random
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app import models as m
from app.core.security import hash_password
from app.services import rag
from app.services.health_svc import get_or_create_settings

RNG = random.Random(42)


def seed_if_empty(db: Session) -> None:
    if db.query(m.User).count() > 0:
        return

    user = m.User(username="admin", nickname="演示同学",
                  password_hash=hash_password("admin123"), is_demo=True)
    db.add(user)
    db.flush()
    uid = user.id

    # ── 课程 ──
    courses = [
        ("高等数学A", "王教授", "三教201", "#38bdf8", [(1, "08:00", "09:40"), (3, "10:00", "11:40"), (5, "08:00", "09:40")]),
        ("英语读写", "李老师", "外院305", "#a78bfa", [(2, "08:00", "09:40"), (4, "08:00", "09:40")]),
        ("数据结构", "张教授", "三教201", "#34d399", [(1, "10:00", "11:40"), (3, "14:00", "15:40")]),
        ("形势与政策", "赵老师", "大礼堂", "#f472b6", [(4, "15:00", "16:40")]),
        ("体育（选项课）", "孙教练", "体育馆", "#fbbf24", [(5, "15:00", "16:40")]),
    ]
    for name, teacher, loc, color, slots in courses:
        c = m.Course(user_id=uid, name=name, teacher=teacher, location=loc, color=color)
        db.add(c)
        db.flush()
        for wd, st, et in slots:
            db.add(m.ClassSlot(course_id=c.id, weekday=wd, start_time=st, end_time=et,
                               start_week=1, end_week=16, weeks_text="1-16周"))

    # ── DDL 任务 ──
    now = datetime.now()
    tasks = [
        ("完成数五作业第5讲", "study", "high", now + timedelta(days=1, hours=7), None),
        ("数据结构实验报告", "study", "medium", now + timedelta(days=3, hours=12), None),
        ("考研报名表信息核对", "life", "high", now + timedelta(hours=20), None),
        ("周度文献阅读笔记", "study", "low", now + timedelta(days=7), None),
        ("购买数学接力题典1800", "life", "low", now - timedelta(days=2), "done"),
        ("整理错题本第七章", "study", "medium", now - timedelta(days=4), "done"),
    ]
    for title, cat, pri, due, status in tasks:
        t = m.Task(user_id=uid, title=title, category=cat, priority=pri, due_at=due)
        if status == "done":
            t.status = "done"
            t.done_at = now - timedelta(days=RNG.randint(1, 5))
            t.progress = 100
        db.add(t)

    # ── 空教室快照：近 4 周工作日 ──
    rooms = [("三教", "101"), ("三教", "102"), ("三教", "201"), ("图书馆", "A区自习室")]
    today = now.date()
    for weeks_ago in range(1, 5):
        for wd in range(1, 6):
            d = today - timedelta(days=today.isoweekday() - wd + 7 * weeks_ago)
            for hour in (9, 10, 12, 14, 15, 18, 20):
                for building, room in rooms:
                    occupied = 1 if RNG.random() < (0.62 if hour in (10, 14, 15, 20) else 0.3) else 0
                    db.add(m.ClassroomRecord(
                        user_id=uid, building=building, room=room, occupied=occupied,
                        note=RNG.choice([None, "座无虚席", "空一大片", "有同学在睡"]),
                        weekday=d.isoweekday(), hour=hour,
                        visited_at=datetime(d.year, d.month, d.day, hour, RNG.randint(0, 59)),
                    ))

    # ── 学习打卡：近 12 天（留 1 天断签） ──
    subjects = ["高数", "英语", "408选择题", "专业课阅读"]
    gap_day = RNG.randint(3, 9)
    for i in range(1, 13):
        d = today - timedelta(days=i)
        if i == gap_day:
            continue
        for _ in range(RNG.randint(1, 2)):
            db.add(m.CheckinRecord(
                user_id=uid, subject=RNG.choice(subjects),
                minutes=RNG.choice([45, 60, 90, 120, 150]),
                content=RNG.choice([None, "完成一章习题", "真题两套", "单词 200 个"]),
                mood=RNG.choice([3, 4, 4, 5]), date=d,
                created_at=datetime(d.year, d.month, d.day, RNG.randint(8, 22), 0),
            ))

    # ── 财务：近 6 个月 ──
    study_cats = [
        ("考研数学网课", 299, "课程", True), ("接力题典1800", 89, "书籍", True),
        ("四级真题卷", 25, "书籍", True), ("打印资料", 36, "学习", True),
    ]
    life_cats = [("食堂", 28, "餐饮"), ("食堂", 35, "餐饮"), ("奶茶", 15, "餐饮"),
                 ("地铁充值", 50, "交通"), ("电影", 45, "娱乐"), ("日用品", 66, "购物")]
    for back in range(6):
        y, mth = today.year, today.month - back
        while mth <= 0:
            mth += 12
            y -= 1
        first = date(y, mth, 1)
        last_day = (date(y + (mth == 12), (mth % 12) + 1, 1) - timedelta(days=1)).day
        dim = last_day
        db.add(m.FinanceRecord(user_id=uid, type="income", category="生活费",
                               amount=1500, occurred_at=date(y, mth, min(1, dim))))
        if RNG.random() < 0.5:
            db.add(m.FinanceRecord(user_id=uid, type="income", category="兼职",
                                   amount=RNG.randint(300, 800), occurred_at=date(y, mth, RNG.randint(5, dim))))
        for day in range(1, dim + 1):
            d = date(y, mth, day)
            if d > today:
                break
            for amount, cat in [(RNG.randint(20, 45), "餐饮"), (RNG.choice([0, 0, 10, 20]), None)]:
                if cat is None and amount == 0:
                    continue
                if RNG.random() < 0.7:
                    db.add(m.FinanceRecord(user_id=uid, type="expense", category=cat or "餐饮",
                                           amount=amount or RNG.randint(10, 40), occurred_at=d))
        for name, amount, cat, is_study in RNG.sample(study_cats, RNG.randint(1, 2)):
            db.add(m.FinanceRecord(user_id=uid, type="expense", category=cat, amount=amount,
                                   is_study=is_study, note=name, occurred_at=date(y, mth, RNG.randint(1, min(20, dim)))))
        for name, amount, cat in RNG.sample(life_cats, RNG.randint(2, 4)):
            db.add(m.FinanceRecord(user_id=uid, type="expense", category=cat, amount=amount,
                                   note=name, occurred_at=date(y, mth, RNG.randint(1, min(25, dim)))))
    db.add(m.Budget(user_id=uid, month=f"{today.year:04d}-{today.month:02d}", category="*", limit_amount=2000))

    # ── 考研目标 ──
    exam_year = today.year + (1 if today.month >= 12 else 0)
    goal = m.KaoyanGoal(
        user_id=uid, target_school="华中科技大学", target_major="计算机技术",
        target_year=exam_year, exam_date=date(exam_year, 12, 21),
        total_target=380, total_current=245,
        detail={"subjects": {
            "政治": {"target": 65, "current": 45, "max": 100},
            "英语一": {"target": 65, "current": 40, "max": 100},
            "数学一": {"target": 105, "current": 75, "max": 150},
            "专业课408": {"target": 145, "current": 85, "max": 150},
        }},
    )
    db.add(goal)
    db.flush()
    exam_days = (goal.exam_date - today).days
    p1 = m.PlanPhase(goal_id=goal.id, name="基础强化期", start_date=today,
                     end_date=today + timedelta(days=int(exam_days * 0.4)),
                     objective="数学 1800 基础篇刷完两轮；408 数据结构+计组一轮；英语真题阅读每日一篇精读",
                     sort_no=1, status="active")
    p2 = m.PlanPhase(goal_id=goal.id, name="真题冲刺期", start_date=today + timedelta(days=int(exam_days * 0.4)),
                     end_date=today + timedelta(days=int(exam_days * 0.75)),
                     objective="数学真题套卷一周两套；408 真题按考点专项；政治背诵手册启动",
                     sort_no=2)
    p3 = m.PlanPhase(goal_id=goal.id, name="考前点睛期", start_date=today + timedelta(days=int(exam_days * 0.75)),
                     end_date=goal.exam_date, objective="全真模拟 + 错题回炉 + 政治大题背诵", sort_no=3)
    db.add_all([p1, p2, p3])
    db.flush()
    daily_pool = [
        ("数学：1800 基础篇 1.5 小时", "数学", 90), ("英语：真题阅读 1 篇精读", "英语", 60),
        ("408：数据结构章节刷题", "408", 90), ("政治：核心考案 30 分钟", "政治", 30),
    ]
    for i in range(4):
        d = today + timedelta(days=i - 1)
        for j, (title, sub, mins) in enumerate(daily_pool):
            db.add(m.PlanTask(phase_id=p1.id, date=d, title=title, subject=sub, planned_minutes=mins,
                              done=(i == 0), done_minutes=mins - 10 if i == 0 else None))

    # ── 知识库 ──
    docs = [
        ("考研数学·中值定理速查", "备考", """# 中值定理速查

## 罗尔定理
f 在 [a,b] 连续、(a,b) 可导、f(a)=f(b)，则存在 ξ 使 f'(ξ)=0。
常见构造：F(x)=f(x)-kx、F(x)=e^{λx}f(x)。

## 拉格朗日中值定理
f(b)-f(a)=f'(ξ)(b-a)。证明不等式优先考虑区间长度拆法。

## 柯西中值定理
两个函数比值形态：[f(b)-f(a)]/[g(b)-g(a)] = f'(ξ)/g'(ξ)，g'≠0。

## 泰勒展开
带 f'' 或 e^x、sin x 的估计题，用二阶泰勒展开配拉格朗日余项。

## 做题口诀
看到 f(a)=f(b) 想罗尔；看到 f(b)-f(a) 想拉氏；看到 f'/g' 想柯西；看到二阶导想泰勒。"""),
        ("408·数据结构高频口诀卡", "备考", """# 数据结构口诀卡

- 栈：后进先出LIFO；队列：先进先出FIFO。
- 完全二叉树第 i 个孩子：2i 与 2i+1；第 i 个父：⌊i/2⌋。
- 哈夫曼树没有度为 1 的节点；n 个叶子总结点 2n-1。
- 快排平均 O(nlogn)，最坏 O(n²)（基本有序+固定基准）；不稳定。
- 堆排序：建堆 O(n)，每次调整 O(logn)，不稳定。
- 归并稳定，空间 O(n)；基数稳定，适合位数少的整数。
- KMP next 数组：从 -1 开始，j 回退到 next[j]。
- B+树：非叶只存索引，叶子链表支持范围查询——数据库默认结构。"""),
    ]
    for title, cat, content in docs:
        doc = m.KnowledgeDoc(user_id=uid, title=title, category=cat, source="manual",
                             file_type="md", content=content)
        db.add(doc)
        db.flush()
        rag.build_index(db, doc)

    # ── 健康 ──
    get_or_create_settings(db, uid)
    for i in range(1, 8):
        d = today - timedelta(days=i)
        db.add(m.HealthLog(user_id=uid, kind="sleep",
                           happened_at=datetime(d.year, d.month, d.day, 8, 0),
                           minutes=RNG.randint(380, 470), date=d))
        db.add(m.HealthLog(user_id=uid, kind="water",
                           happened_at=datetime(d.year, d.month, d.day, 20, 0),
                           value=RNG.choice([1200, 1500, 1800, 2000]), date=d))
        if RNG.random() < 0.55:
            db.add(m.HealthLog(user_id=uid, kind="exercise",
                               happened_at=datetime(d.year, d.month, d.day, RNG.randint(16, 19), 0),
                               minutes=RNG.choice([30, 40, 45]), date=d))

    db.commit()
