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
