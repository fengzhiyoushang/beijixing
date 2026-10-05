"""检查已导入的教室课表数据，找出含周次约束（如 2-16周双）的课，用于验证按日期精确判定。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.core.database import SessionLocal
from app.models.course import Course, CourseSchedule, Semester
from app.models.pdf_schedule import PdfScheduleEntry

db = SessionLocal()

print("── 学期 ──")
for s in db.query(Semester).all():
    print(f"  id={s.id} {s.name} start={s.start_date} weeks={s.total_weeks} current={s.is_current}")

print("\n── 教室课表（Course.source == 'classroom'）──")
courses = db.query(Course).filter(Course.source == "classroom").all()
print(f"  共 {len(courses)} 门")
slots = (db.query(CourseSchedule).join(Course, CourseSchedule.course_id == Course.id)
         .filter(Course.source == "classroom").all())
print(f"  共 {len(slots)} 个时段")
print("\n  前 25 条时段（地点 / 星期 / 时间 / 周次）：")
for sl in slots[:25]:
    c = db.get(Course, sl.course_id)
    print(f"    {c.name[:16]:<18} 周{sl.weekday} {sl.start_time}-{sl.end_time} "
          f"周次={sl.weeks!r} 地点={sl.location!r}")

# 统计周次表达式分布
from collections import Counter
wc = Counter(sl.weeks or "(空)" for sl in slots)
print("\n  周次表达式分布：", dict(wc.most_common(12)))

print("\n── PDF 课表条目 ──")
pdfs = db.query(PdfScheduleEntry).all()
print(f"  共 {len(pdfs)} 条")
wc2 = Counter(e.weeks or "(空)" for e in pdfs)
print("  周次表达式分布：", dict(wc2.most_common(12)))
print("\n  前 15 条：")
for e in pdfs[:15]:
    print(f"    {e.course_name[:16]:<18} 周{e.weekday} {e.start_time}-{e.end_time} "
          f"周次={e.weeks!r} 地点={e.location!r} 教室={e.room_no!r}")

db.close()
