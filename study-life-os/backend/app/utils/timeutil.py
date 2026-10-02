"""时间工具：时间串比较、月/周区间、免打扰时段判断等。"""
from datetime import date, datetime, time


def to_minutes(hm: str) -> int:
    try:
        h, m = str(hm).split(":")
        return int(h) * 60 + int(m)
    except Exception:
        return 0


def ranges_overlap(a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
    """[) 语义的时间区间相交判断。"""
    return to_minutes(a_start) < to_minutes(b_end) and to_minutes(b_start) < to_minutes(a_end)


def weeks_intersect(a: tuple, b: tuple) -> bool:
    a_s, a_e = a
    b_s, b_e = b
    return a_s <= b_e and b_s <= a_e


def month_str(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def parse_month(month: str) -> tuple[date, date]:
    """返回 (当月首日, 下月首日)。"""
    y, m = int(month[:4]), int(month[5:7])
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def in_time_range(now: time, start: str, end: str) -> bool:
    """支持跨天区间（如 23:00~07:00）。"""
    s = time(*map(int, start.split(":")))
    e = time(*map(int, end.split(":")))
    if s <= e:
        return s <= now <= e
    return now >= s or now <= e


def week_bounds(d: date) -> tuple[date, date]:
    monday = d - timedelta_days(d.weekday())
    return monday, monday + timedelta_days(6)


def timedelta_days(n: int):
    from datetime import timedelta
    return timedelta(days=n)


def now_naive() -> datetime:
    return datetime.now()
