"""空教室「精确日期 + 时间段」查询的针对性验证（不依赖 HTTP 服务，直接调服务层）。"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.utils.timeutil import (date_of_week_day, normalize_semester_start, parse_weeks,
                                week_of_date, week_range)

failures: list[str] = []


def check(label: str, got, want):
    ok = got == want
    print(f"{'✓' if ok else '✗'} {label:<58} got={got!r}" + ("" if ok else f"  want={want!r}"))
    if not ok:
        failures.append(label)


print("── 1. 学期起始日对齐周一（2025-08-31 是周日 → 归到 2025-08-25 周一）──")
check("normalize(2025-08-31)", normalize_semester_start(date(2025, 8, 31)), date(2025, 8, 25))
check("normalize(2025-09-01 周一) 保持不变",
      normalize_semester_start(date(2025, 9, 1)), date(2025, 9, 1))

print("\n── 2. 以 2025-09-01（周一）为第 1 周，日期 → 周次 ──")
START = date(2025, 9, 1)
cases = [
    (date(2025, 9, 1), 1), (date(2025, 9, 2), 1), (date(2025, 9, 7), 1),
    (date(2025, 9, 8), 2), (date(2025, 9, 14), 2),
    (date(2025, 10, 1), 5), (date(2025, 10, 5), 5),
    (date(2025, 10, 6), 6), (date(2025, 11, 3), 10), (date(2025, 11, 9), 10),
    (date(2025, 11, 10), 11), (date(2025, 12, 22), 17),
]
for d, want in cases:
    check(f"{d} → 第 {want} 周", week_of_date(START, d), want)

print("\n── 3. 周次 + 星期 → 具体日期（往返一致）──")
for wk in (1, 5, 10, 17):
    for wd in (1, 3, 7):
        d = date_of_week_day(START, wk, wd)
        back = week_of_date(START, d)
        check(f"第{wk}周 周{wd} → {d} → 回推第{back}周", back, wk)

print("\n── 4. 周范围 ──")
check("第 1 周范围", week_range(START, 1), (date(2025, 9, 1), date(2025, 9, 7)))
check("第 10 周范围", week_range(START, 10), (date(2025, 11, 3), date(2025, 11, 9)))

print("\n── 5. 学期外日期返回 None（不夹取为 1）──")
check("2025-08-20（学期前）", week_of_date(START, date(2025, 8, 20)), None)

print("\n── 6. 周次表达式与日期判定（Excel 常见写法）──")
# 探针周：第1(单)、第2(双)、第10(双)、第11(单)
exprs = {
    # expr: (含第1周, 含第2周, 含第10周, 含第11周)
    "1-16": (True, True, True, True),
    "2-16周双": (False, True, True, False),      # 双周：2,4,...,10,12...；10 偶→含，11 奇→不含
    "1-16单": (True, False, False, True),        # 单周：1,3,...,9,11...；10 偶→不含，11 奇→含
    "1,3,5-9": (True, False, False, False),      # 仅 1,3,5,6,7,8,9
}
for expr, want in exprs.items():
    weeks = parse_weeks(expr, 20)
    for probe, expect in zip((1, 2, 10, 11), want):
        check(f"'{expr}' 含第{probe}周", probe in weeks, expect)

print("\n── 6b. 单双周边界补充校验 ──")
check("'2-16周双' 含第12周", 12 in parse_weeks("2-16周双", 20), True)
check("'2-16周双' 含第13周", 13 in parse_weeks("2-16周双", 20), False)
check("'1-16单' 含第9周", 9 in parse_weeks("1-16单", 20), True)
check("'1-16单' 含第16周", 16 in parse_weeks("1-16单", 20), False)

print("\n── 7. 具体日期 → 该课是否上课（端到端判定）──")
# 模拟 Excel 中的两门课
courses = [
    {"name": "操作系统", "weekday": 1, "start": "08:00", "end": "09:40", "weeks": "1-16"},
    {"name": "网络实验", "weekday": 1, "start": "08:00", "end": "09:40", "weeks": "2-16周双"},
]
def has_class(d: date, hour: int = 8) -> list[str]:
    wk = week_of_date(START, d)
    hit = []
    for c in courses:
        if c["weekday"] != d.isoweekday():
            continue
        if wk is None or wk not in parse_weeks(c["weeks"], 20):
            continue
        if int(c["start"][:2]) <= hour < int(c["end"][:2]) + 1:
            hit.append(c["name"])
    return hit

check("2025-09-01(周一,第1周,08时)", has_class(date(2025, 9, 1)), ["操作系统"])
check("2025-09-08(周一,第2周,08时)", has_class(date(2025, 9, 8)), ["操作系统", "网络实验"])
check("2025-09-15(周一,第3周,08时)", has_class(date(2025, 9, 15)), ["操作系统"])
check("2025-09-22(周一,第4周,08时)", has_class(date(2025, 9, 22)), ["操作系统", "网络实验"])
check("2025-09-01 的 10 时无课", has_class(date(2025, 9, 1), 10), [])
check("2025-09-02(周二) 无课", has_class(date(2025, 9, 2)), [])

print("\n" + ("✅ 全部通过" if not failures else f"❌ {len(failures)} 项失败：{failures}"))
sys.exit(0 if not failures else 1)
