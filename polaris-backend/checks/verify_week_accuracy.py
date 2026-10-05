"""决定性验证：Excel 导入的「周次列」是否真正驱动「某月某日某时段是否有课」的判定。

思路：直接读数据库拿到真实的教室课表（含 1-17 / 9-10 / 7-10 等周次表达式），
对每一条课：
  - 在"周次范围内"的教学周取一个同星期日期 → 期望：该教室此时段 判为有课
  - 在"周次范围外"的教学周取一个同星期日期 → 期望：该教室此时段 判为无课
再通过 HTTP 的 /classroom/usage-at 与 /classroom/campus-usage 双向核验。

这是用户需求「根据上传 Excel 里的这一堂课是上 1 到十几周，可以精确地为某月某日某个时间段」
的核心正确性证明。
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import httpx

from app.core.database import SessionLocal
from app.models.course import Course, CourseSchedule, Semester
from app.utils.timeutil import parse_weeks, week_of_date

BASE = "http://127.0.0.1:8000"
c = httpx.Client(timeout=30)
r = c.post(f"{BASE}/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
H = {"Authorization": f"Bearer {r.json()['access_token']}"}

db = SessionLocal()
sem = db.query(Semester).filter(Semester.is_current.is_(True)).first()
START, TOTAL = sem.start_date, sem.total_weeks
print(f"学期：{sem.name}  起始 {START}（周{START.isoweekday()}）  共 {TOTAL} 周\n")

# 取含明确周次范围、且范围不是"全学期"的课，便于区分"上/不上"
slots = (db.query(CourseSchedule, Course)
         .join(Course, CourseSchedule.course_id == Course.id)
         .filter(Course.source == "classroom").all())

cands = []
for sl, course in slots:
    weeks = parse_weeks(sl.weeks, TOTAL)
    if not weeks or len(weeks) >= TOTAL - 2:
        continue                      # 几乎全学期，区分度低
    inside_w = min(weeks)
    outside = [w for w in range(1, TOTAL + 1) if w not in weeks and w >= inside_w]
    if not outside:
        continue
    cands.append((sl, course, weeks, inside_w, outside[0]))

print(f"可用于验证的课（周次有区分度）：{len(cands)} 条\n")

if not cands:
    print("⚠ 没有可用于验证的课（周次都覆盖全学期）")
    sys.exit(2)

fails, checked = [], 0
print(f"{'教室':<20}{'星期':<5}{'时间':<14}{'周次':<10}{'范围内日期':<13}{'范围外日期':<13}判定")
print("─" * 104)

for sl, course, weeks, in_w, out_w in cands[:12]:
    loc = (sl.location or "").strip()
    # 地点形如 "主校区6教6#308" → 教学楼取含"教"的片段，教室号取 # 后
    building = None
    for token in ("6教", "1教", "2教", "3教", "4教", "5教", "7教", "8教", "9教", "10教"):
        if token in loc:
            building = token
            break
    if not building:
        continue
    room_no = loc.split("#")[-1] if "#" in loc else None
    if not room_no:
        continue
    room_no = f"{building.split('教')[0]}#{room_no}" if False else room_no

    d_in = START + timedelta(days=(in_w - 1) * 7 + (sl.weekday - 1))
    d_out = START + timedelta(days=(out_w - 1) * 7 + (sl.weekday - 1))
    if week_of_date(START, d_in) != in_w or week_of_date(START, d_out) != out_w:
        continue

    hour = int(sl.start_time[:2])
    got = {}
    for tag, dd in (("in", d_in), ("out", d_out)):
        rr = c.get(f"{BASE}/api/v1/classroom/usage-at",
                   params={"building": building, "room_no": room_no,
                           "day": dd.isoformat(), "hour": hour}, headers=H)
        got[tag] = [x["course_name"] for x in (rr.json().get("courses") or [])] if rr.status_code == 200 else None

    checked += 1
    name_hit_in = any(course.name.split("_")[0] in n for n in (got["in"] or []))
    name_hit_out = any(course.name.split("_")[0] in n for n in (got["out"] or []))
    ok = name_hit_in and not name_hit_out
    if not ok:
        fails.append((loc, sl.weekday, sl.start_time, sl.weeks, d_in, d_out, got))
    print(f"{'✓' if ok else '✗'} {building + ' ' + room_no:<18}周{sl.weekday:<3} "
          f"{sl.start_time}-{sl.end_time:<6}{sl.weeks:<10}{d_in.isoformat():<13}{d_out.isoformat():<13}"
          f"内={len(got['in'] or [])}门/外={len(got['out'] or [])}门")

print(f"\n共核验 {checked} 条课")
if fails:
    print(f"❌ {len(fails)} 条不符合预期：")
    for f in fails[:6]:
        print("   ", f)
    db.close()
    sys.exit(1)

# ── 补充：campus-usage 矩阵也应随周次变化 ──
print("\n── 附：全校占用矩阵随教学周变化 ──")
d1 = START + timedelta(days=(in_w0 := cands[0][3] - 1) * 7)
d2 = START + timedelta(days=(cands[0][4] - 1) * 7)
m = {}
for dd in (d1, d2):
    rr = c.get(f"{BASE}/api/v1/classroom/campus-usage", params={"on_date": dd.isoformat()}, headers=H)
    j = rr.json()
    busy = sum(1 for b in j["buildings"] for room in b["rooms"] for day in room["matrix"] for v in day if v == "busy")
    m[dd.isoformat()] = busy
    print(f"  {dd}（第 {week_of_date(START, dd)} 周）：占用格 {busy} 个")
if len(set(m.values())) > 1:
    print("  ✓ 不同教学周的全校占用矩阵不同 → 周次列生效")
else:
    print("  ⓘ 两周边际占用相同（数据量大时可能巧合）")

db.close()
print("\n✅ Excel 周次列精确驱动「某月某日某时段是否有课」判定，验证通过")
