"""课程时间段冲突检测：同 weekday、时间重叠且周次相交即冲突。"""
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models.course import ClassSlot, Course
from app.utils.timeutil import ranges_overlap, weeks_intersect

FULL_WEEKS = (1, 25)


def _slot_weeks(s) -> tuple[int, int]:
    start = getattr(s, "start_week", None) or 1
    end = getattr(s, "end_week", None) or 25
    return start, end


def find_conflicts(
    db: Session,
    user_id: int,
    slots: Iterable,
    exclude_course_id: Optional[int] = None,
    course_name: str = "新课",
) -> list[dict]:
    """slots 可为 SlotIn 列表或 (weekday,start,end,ws,we) 元组序列。"""
    mine = []
    for s in slots:
        if hasattr(s, "weekday"):
            mine.append({
                "weekday": s.weekday,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "weeks": _slot_weeks(s),
            })
        else:
            wd, st, et, ws, we = s
            mine.append({"weekday": wd, "start_time": st, "end_time": et,
                         "weeks": (ws or 1, we or 25)})

    query = (
        db.query(ClassSlot, Course)
        .join(Course, ClassSlot.course_id == Course.id)
        .filter(Course.user_id == user_id)
    )
    if exclude_course_id:
        query = query.filter(Course.id != exclude_course_id)
    others = query.all()

    conflicts: list[dict] = []
    for slot in mine:
        for other_slot, other_course in others:
            if other_slot.weekday != slot["weekday"]:
                continue
            if not ranges_overlap(slot["start_time"], slot["end_time"],
                                  other_slot.start_time, other_slot.end_time):
                continue
            if not weeks_intersect(slot["weeks"], _slot_weeks(other_slot)):
                continue
            conflicts.append({
                "slot": slot,
                "conflict_course": other_course.name,
                "conflict_slot": other_slot.to_dict(),
                "location": other_course.location,
            })
    return conflicts
