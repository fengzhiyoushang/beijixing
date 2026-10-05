"""时间与周次工具：节次换算、周次解析、区间重叠、周次相交。"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

WEEKDAY_CN = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]

# 默认作息：第 1 节 08:00 开始，每节 45 分钟
SECTION_START = {
    1: "08:00", 2: "08:55", 3: "10:00", 4: "10:55",
    5: "14:00", 6: "14:55", 7: "16:00", 8: "16:55",
    9: "19:00", 10: "19:55", 11: "20:50", 12: "21:45",
}


def to_minutes(hhmm: str) -> int:
    """'08:30' → 510（分钟）；支持跨天（< 5 点视为次日）。"""
    h, m = (int(x) for x in hhmm.split(":"))
    total = h * 60 + m
    return total + 24 * 60 if h < 5 else total


def ranges_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    a1, a2 = to_minutes(start_a), to_minutes(end_a)
    b1, b2 = to_minutes(start_b), to_minutes(end_b)
    return a1 < b2 and b1 < a2


def section_to_time(section: int) -> str:
    return SECTION_START.get(section, "08:00")


def parse_weeks(expr: str | None, total_weeks: int = 20) -> set[int]:
    """解析周次表达式：'1-16'、'1-16单'、'1,3,5-9'、'2-16双'。"""
    if not expr:
        return set(range(1, total_weeks + 1))
    # "第1周"/"1-16周"/"2-16周双" → 去掉"周"与"第"前缀后再解析
    text = expr.strip().replace("周", "").replace("第", "")
    odd = "单" in text
    even = "双" in text
    text = text.replace("单", "").replace("双", "")
    result: set[int] = set()
    for part in re.split(r"[,，]", text):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                a, b = (int(x) for x in part.split("-", 1))
            except ValueError:
                continue
            result.update(range(a, b + 1))
        elif part.isdigit():
            result.add(int(part))
    if odd:
        result = {w for w in result if w % 2 == 1}
    if even:
        result = {w for w in result if w % 2 == 0}
    return result or set(range(1, total_weeks + 1))


def weeks_intersect(a: str | None, b: str | None, total_weeks: int = 20) -> bool:
    return bool(parse_weeks(a, total_weeks) & parse_weeks(b, total_weeks))


def current_week(start_date: date | None, today: date | None = None) -> int:
    """学期开始日期 → 当前教学周（不足一周按第 1 周）。"""
    if not start_date:
        return 1
    today = today or date.today()
    delta = (today - start_date).days
    return max(1, delta // 7 + 1)


# ─────────── 精确日期 ↔ 教学周 换算 ───────────
# 教学周约定：start_date 为第 1 周的周一；第 N 周 = [start + (N-1)*7, start + N*7 - 1]
# 例：2025-08-31（周一）为第 1 周 → 2025-09-01(周一，第 1 周) / 2025-11-03 为第 10 周。

def week_of_date(start_date: date | None, target: date | None = None) -> int | None:
    """指定日期落在教学第几周；学期未设置或不在学期范围内返回 None。

    与 current_week 的区别：不夹取到 >=1，超出学期范围的日期返回 None，
    便于调用方区分「学期外」与「第 1 周」。
    """
    if not start_date:
        return None
    target = target or date.today()
    delta = (target - start_date).days
    if delta < 0:
        return None
    return delta // 7 + 1


def date_of_week_day(start_date: date | None, week: int, weekday: int) -> date | None:
    """教学周 + 星期(1=周一..7=周日) → 具体日期。"""
    if not start_date or week < 1:
        return None
    weekday = max(1, min(7, weekday))
    return start_date + timedelta(days=(week - 1) * 7 + (weekday - 1))


def week_range(start_date: date | None, week: int) -> tuple[date, date] | None:
    """某教学周的起止日期（周一 ~ 周日）。"""
    first = date_of_week_day(start_date, week, 1)
    if not first:
        return None
    return first, first + timedelta(days=6)


def align_to_monday(d: date) -> date:
    """把任意日期归到所在周的周一（教学周对齐用）。"""
    return d - timedelta(days=d.isoweekday() - 1)


def normalize_semester_start(d: date | None) -> date | None:
    """学期起始日归一到周一：保证「8/31 为第 1 周」这类约定成立。"""
    return align_to_monday(d) if d else None


def semester_bounds(start: date, total_weeks: int) -> tuple[date, date]:
    return start, start + timedelta(weeks=total_weeks) - timedelta(days=1)


def weekday_of(d: date | None = None) -> int:
    """1=周一 … 7=周日（与数据库 weekday 字段一致）。"""
    d = d or date.today()
    return d.isoweekday()


def fmt_dt(value: datetime | None) -> str | None:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else None


def month_str(d: date | None = None) -> str:
    d = d or date.today()
    return f"{d.year:04d}-{d.month:02d}"


def month_range(month: str) -> tuple[date, date]:
    """'2026-10' → (2026-10-01, 2026-10-31)。"""
    year, mon = (int(x) for x in month.split("-"))
    first = date(year, mon, 1)
    next_first = date(year + (mon // 12), (mon % 12) + 1, 1)
    return first, next_first - timedelta(days=1)


def last_months(n: int, end: date | None = None) -> list[str]:
    end = end or date.today()
    out = []
    y, m = end.year, end.month
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return list(reversed(out))
