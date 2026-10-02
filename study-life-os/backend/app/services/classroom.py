"""空教室规律分析与空闲预测。

规律分析：按 (weekday, hour) 桶聚合拍照快照 → 空闲率矩阵。
空闲预测：时间衰减加权的个人空闲率，叠加「本人课程占用」与「全校课程占用」惩罚，输出 0~100 置信分。
"""
import math
import re
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models.classroom import ClassroomRecord
from app.models.course import ClassSlot, Course
from app.utils.timeutil import ranges_overlap, to_minutes

WORK_HOURS = list(range(8, 22))  # 教学时段 8:00~22:00
MIN_SAMPLES = 2                  # 低于该样本量视为数据不足


def _room_in_locs(room: str, locs) -> bool:
    """教室号是否出现在地点串中（前后非数字，避免 201 误匹配 1201）。"""
    if not room:
        return False
    pattern = re.compile(rf"(?<!\d){re.escape(room)}(?!\d)")
    return any(pattern.search(loc or "") for loc in locs)


def list_buildings(db: Session, user_id: int) -> list[dict]:
    rows = (
        db.query(ClassroomRecord.building, ClassroomRecord.room)
        .filter(ClassroomRecord.user_id == user_id)
        .distinct()
        .all()
    )
    grouped: dict[str, list[str]] = defaultdict(list)
    for b, r in rows:
        if r not in grouped[b]:
            grouped[b].append(r)
    return [{"building": b, "rooms": sorted(rs)} for b, rs in sorted(grouped.items())]


def room_pattern(db: Session, user_id: int, building: str, room: str) -> dict:
    """weekday×hour 空闲率矩阵，供 Web 热力图渲染。"""
    records = (
        db.query(ClassroomRecord)
        .filter(
            ClassroomRecord.user_id == user_id,
            ClassroomRecord.building == building,
            ClassroomRecord.room == room,
        )
        .all()
    )
    matrix = []
    for wd in range(1, 8):
        row = []
        for hour in WORK_HOURS:
            bucket = [r for r in records if r.weekday == wd and r.hour == hour]
            total = len(bucket)
            free = sum(1 for r in bucket if not r.occupied)
            row.append({"weekday": wd, "hour": hour, "total": total,
                        "free": free, "rate": round(free / total, 3) if total else None})
        matrix.append(row)
    return {
        "building": building, "room": room,
        "samples": len(records),
        "hours": WORK_HOURS,
        "matrix": matrix,
        "enough_data": len(records) >= MIN_SAMPLES * 4,
    }


def _course_slot_keys(db: Session, user_id: int | None, weekday: int, hour: int,
                     exclude_user: bool = False) -> set[tuple[str, str]]:
    """指定 weekday×hour 时段内被课程占用的 (building_key, room) 集合。"""
    hour_start, hour_end = f"{hour:02d}:00", f"{hour + 1:02d}:00"
    query = (
        db.query(ClassSlot, Course)
        .join(Course, ClassSlot.course_id == Course.id)
        .filter(ClassSlot.weekday == weekday)
    )
    if user_id is not None:
        query = query.filter(Course.user_id == user_id)
    hits: set[tuple[str, str]] = set()
    for slot, course in query.all():
        if not ranges_overlap(slot.start_time, slot.end_time, hour_start, hour_end):
            continue
        loc = (course.location or "").strip()
        if loc:
            hits.add((course.name, loc))
    return hits


def predict(db: Session, user_id: int, weekday: int | None = None,
            hour: int | None = None, days_back: int = 90) -> dict:
    """空闲预测：返回按置信分排序的教室候选。"""
    now = datetime.now()
    weekday = weekday or now.isoweekday()
    hour = hour if hour is not None else now.hour

    since = now - timedelta(days=days_back)
    records = (
        db.query(ClassroomRecord)
        .filter(
            ClassroomRecord.user_id == user_id,
            ClassroomRecord.weekday == weekday,
            ClassroomRecord.visited_at >= since,
        )
        .all()
    )
    if not records:
        return {"weekday": weekday, "hour": hour, "results": [],
                "hint": "该时段尚无历史快照，请到小程序「空教室」页拍照采集数据。"}

    # 本人课程直接排除（该时段要去上课的教室没意义）
    self_busy_locs = {loc for _, loc in _course_slot_keys(db, user_id, weekday, hour)}
    all_busy_locs = [loc for _, loc in _course_slot_keys(db, None, weekday, hour)]

    buckets: dict[tuple[str, str], list[ClassroomRecord]] = defaultdict(list)
    for r in records:
        buckets[(r.building, r.room)].append(r)

    results = []
    for (building, room), recs in buckets.items():
        if _room_in_locs(room, self_busy_locs):
            continue  # 自己这节就要去这里上课
        # 同小时桶 + 相邻小时加权（1 小时邻域 ×0.6）
        weighted_free = weighted_total = 0.0
        for r in recs:
            if abs(r.hour - hour) > 1:
                continue
            decay = math.exp(-0.05 * max((now - r.visited_at).days, 0))
            weight = decay * (1.0 if r.hour == hour else 0.6)
            weighted_total += weight
            if not r.occupied:
                weighted_free += weight
        if weighted_total <= 0 or len(recs) < MIN_SAMPLES:
            continue
        score = weighted_free / weighted_total

        penalty = 0.0
        if _room_in_locs(room, all_busy_locs):
            penalty += 0.35  # 被任意课程点名占用
        final = max(0.0, min(1.0, score - penalty))
        recent = max((r.visited_at for r in recs), default=None)
        last_occupied = None
        if recent:
            last = sorted([r for r in recs if r.visited_at == recent], key=lambda x: -x.id)[0]
            last_occupied = bool(last.occupied)
        results.append({
            "building": building,
            "room": room,
            "confidence": round(final * 100),
            "samples": len(recs),
            "last_visited": recent.isoformat() if recent else None,
            "last_occupied": last_occupied,
        })

    results.sort(key=lambda x: -x["confidence"])
    return {
        "weekday": weekday,
        "hour": hour,
        "results": results[:10],
        "hint": None if results else "历史样本不足，请继续采集后获得更准预测。",
    }
