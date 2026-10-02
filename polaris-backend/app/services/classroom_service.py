"""空教室服务：教室管理、状态上报、空闲概率统计、预测推荐、VL 识图落库。"""
from __future__ import annotations

import io
import json
import logging
import math
import re
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.ai.deepseek import deepseek
from app.core.exceptions import AppError, NotFoundError
from app.models.classroom import Classroom, ClassroomStatusLog, ClassroomUsageRecord
from app.models.course import Course, CourseSchedule, Semester
from app.models.pdf_schedule import PdfScheduleEntry, PdfScheduleUpload
from app.utils.timeutil import (current_week, parse_weeks, ranges_overlap, to_minutes, weekday_of)

logger = logging.getLogger("polaris.classroom")

WORK_HOURS = list(range(8, 23))     # 教学时段 8:00~22:00
MIN_SAMPLES = 2                     # 少于该样本量不参与预测


# ─────────── 教室信息管理 ───────────
def get_or_create_classroom(db: Session, building: str, room_no: str, **defaults) -> Classroom:
    room = (db.query(Classroom)
            .filter(Classroom.building == building, Classroom.room_no == room_no)
            .first())
    if room:
        return room
    room = Classroom(building=building, room_no=room_no, **defaults)
    db.add(room)
    db.flush()
    return room


def get_classroom(db: Session, classroom_id: int) -> Classroom:
    room = db.get(Classroom, classroom_id)
    if not room:
        raise NotFoundError("教室不存在")
    return room


def list_classrooms(db: Session, *, building: str | None = None, room_type: str | None = None,
                    keyword: str | None = None, only_active: bool = True) -> list[Classroom]:
    query = db.query(Classroom)
    if only_active:
        query = query.filter(Classroom.is_active.is_(True))
    if building:
        query = query.filter(Classroom.building == building)
    if room_type:
        query = query.filter(Classroom.room_type == room_type)
    if keyword:
        query = query.filter(Classroom.room_no.like(f"%{keyword}%"))
    return query.order_by(Classroom.building, Classroom.room_no).all()


def list_buildings(db: Session) -> list[dict]:
    rows = db.query(Classroom.building, Classroom.room_no).distinct().all()
    grouped: dict[str, list[str]] = defaultdict(list)
    for building, room_no in rows:
        grouped[building].append(room_no)
    return [{"building": b, "rooms": sorted(set(v)), "count": len(set(v))}
            for b, v in sorted(grouped.items())]


def building_usage(db: Session, building: str, *, days_back: int = 120,
                   user_id: int | None = None) -> dict:
    """某教学楼内每间教室的 weekday×hour 使用状态（绿=空闲/红=占用/灰=无数据）。

    每个格子按该时段历史快照多数表决：free 多数→空闲，busy 多数→占用，无样本→null。
    一次查询整楼日志，避免逐间请求。
    """
    rooms = (db.query(Classroom)
             .filter(Classroom.building == building, Classroom.is_active == True)  # noqa: E712
             .order_by(Classroom.floor, Classroom.room_no).all())
    if not rooms:
        return {"building": building, "hours": WORK_HOURS, "days": list(range(1, 8)), "rooms": []}

    since = datetime.now() - timedelta(days=days_back)
    query = (db.query(ClassroomStatusLog.room_no, ClassroomStatusLog.weekday,
                      ClassroomStatusLog.hour, ClassroomStatusLog.status)
             .filter(ClassroomStatusLog.building == building,
                     ClassroomStatusLog.recorded_at >= since))
    if user_id:
        query = query.filter(ClassroomStatusLog.user_id == user_id)

    # (room, weekday, hour) -> [free_count, busy_count]
    cells: dict[tuple[str, int, int], list[int]] = defaultdict(lambda: [0, 0])
    room_samples: dict[str, int] = defaultdict(int)
    for room_no, weekday, hour, status in query.all():
        room_samples[room_no] += 1
        if status == "free":
            cells[(room_no, weekday, hour)][0] += 1
        elif status == "busy":
            cells[(room_no, weekday, hour)][1] += 1

    out_rooms = []
    sched_busy, sched_known = _schedule_busy_map(db, user_id=user_id)
    for room in rooms:
        key = (room.building, room.room_no)
        room_busy = sched_busy.get(key, frozenset())
        matrix = []
        for weekday in range(1, 8):
            row = []
            for hour in WORK_HOURS:
                if (weekday, hour) in room_busy:
                    row.append("busy")
                    continue
                free, busy = cells.get((room.room_no, weekday, hour), [0, 0])
                total = free + busy
                if total == 0:
                    # 导入过该教室课表但此时段无课 → 空闲；否则未知 → 灰
                    row.append("free" if key in sched_known else None)
                else:
                    row.append("free" if free >= busy else "busy")
            matrix.append(row)
        out_rooms.append({
            "room_no": room.room_no,
            "name": f"{building} {room.room_no}",
            "floor": room.floor,
            "room_type": room.room_type,
            "samples": room_samples.get(room.room_no, 0),
            "matrix": matrix,
        })
    return {"building": building, "hours": WORK_HOURS, "days": list(range(1, 8)), "rooms": out_rooms}


def campus_usage(db: Session, *, days_back: int = 120, user_id: int | None = None) -> dict:
    """全校所有教学楼的使用状态（每楼每间教室 weekday×hour 多数表决），一次返回。"""
    rooms = (db.query(Classroom)
             .filter(Classroom.is_active == True)  # noqa: E712
             .order_by(Classroom.building, Classroom.floor, Classroom.room_no).all())
    since = datetime.now() - timedelta(days=days_back)
    query = (db.query(ClassroomStatusLog.building, ClassroomStatusLog.room_no,
                      ClassroomStatusLog.weekday, ClassroomStatusLog.hour, ClassroomStatusLog.status)
             .filter(ClassroomStatusLog.recorded_at >= since))
    if user_id:
        query = query.filter(ClassroomStatusLog.user_id == user_id)

    cells: dict[tuple[str, str, int, int], list[int]] = defaultdict(lambda: [0, 0])
    room_samples: dict[tuple[str, str], int] = defaultdict(int)
    for building, room_no, weekday, hour, status in query.all():
        room_samples[(building, room_no)] += 1
        if status == "free":
            cells[(building, room_no, weekday, hour)][0] += 1
        elif status == "busy":
            cells[(building, room_no, weekday, hour)][1] += 1

    # 课表占用（导入教室课表 Excel / PDF 课表）：当前教学周有排课的时段直接视为使用
    sched_busy, sched_known = _schedule_busy_map(db, user_id=user_id)

    grouped: dict[str, list] = defaultdict(list)
    for room in rooms:
        key = (room.building, room.room_no)
        room_busy = sched_busy.get(key, frozenset())
        matrix = []
        for weekday in range(1, 8):
            row = []
            for hour in WORK_HOURS:
                if (weekday, hour) in room_busy:
                    row.append("busy")
                    continue
                free, busy = cells.get((room.building, room.room_no, weekday, hour), [0, 0])
                if free + busy == 0:
                    row.append("free" if key in sched_known else None)
                else:
                    row.append("free" if free >= busy else "busy")
            matrix.append(row)
        grouped[room.building].append({
            "room_no": room.room_no,
            "floor": room.floor,
            "samples": room_samples.get((room.building, room.room_no), 0),
            "matrix": matrix,
        })
    return {
        "hours": WORK_HOURS,
        "days": list(range(1, 8)),
        "buildings": [{"building": b, "rooms": r} for b, r in sorted(grouped.items())],
    }


# ─────────── 状态上报 ───────────
def report_status(db: Session, user_id: int | None, payload) -> ClassroomStatusLog:
    recorded_at = payload.recorded_at or datetime.now()
    room = get_or_create_classroom(db, payload.building, payload.room_no)
    log = ClassroomStatusLog(
        classroom_id=room.id,
        user_id=user_id,
        building=payload.building,
        room_no=payload.room_no,
        status=payload.status,
        occupied_seats=payload.occupied_seats,
        source=payload.source,
        confidence=payload.confidence,
        photo_url=payload.photo_url,
        note=payload.note,
        recorded_at=recorded_at,
        weekday=weekday_of(recorded_at.date()),
        hour=recorded_at.hour,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _recent_log_query(db: Session, *, building: str | None = None, room_no: str | None = None,
                      user_id: int | None = None):
    query = db.query(ClassroomStatusLog)
    if user_id:
        query = query.filter(ClassroomStatusLog.user_id == user_id)
    if building:
        query = query.filter(ClassroomStatusLog.building == building)
    if room_no:
        query = query.filter(ClassroomStatusLog.room_no == room_no)
    return query


def recent_logs(db: Session, *, building: str | None = None, room_no: str | None = None,
                limit: int = 20, offset: int = 0, user_id: int | None = None) -> list[ClassroomStatusLog]:
    return (_recent_log_query(db, building=building, room_no=room_no, user_id=user_id)
            .order_by(ClassroomStatusLog.recorded_at.desc()).offset(max(offset, 0)).limit(limit).all())


def count_recent_logs(db: Session, *, building: str | None = None, room_no: str | None = None,
                      user_id: int | None = None) -> int:
    return _recent_log_query(db, building=building, room_no=room_no, user_id=user_id).count()


def delete_status_log(db: Session, log_id: int, user_id: int) -> dict:
    log = db.get(ClassroomStatusLog, log_id)
    if not log:
        raise NotFoundError("采集记录不存在")
    if log.user_id and log.user_id != user_id:
        raise AppError("无权删除他人上报的记录")
    db.delete(log)
    db.commit()
    return {"deleted": True, "id": log_id}


# ─────────── 空闲概率统计 ───────────
def free_rate(db: Session, *, building: str, room_no: str, days_back: int = 120,
              user_id: int | None = None) -> dict:
    """weekday×hour 空闲率矩阵（含样本量、置信区间近似）。"""
    since = datetime.now() - timedelta(days=days_back)
    query = db.query(ClassroomStatusLog).filter(
        ClassroomStatusLog.building == building,
        ClassroomStatusLog.room_no == room_no,
        ClassroomStatusLog.recorded_at >= since,
    )
    if user_id:
        query = query.filter(ClassroomStatusLog.user_id == user_id)
    logs = query.all()

    buckets: dict[tuple[int, int], list[ClassroomStatusLog]] = defaultdict(list)
    for log in logs:
        buckets[(log.weekday, log.hour)].append(log)

    matrix = []
    for weekday in range(1, 8):
        row = []
        for hour in WORK_HOURS:
            items = buckets.get((weekday, hour), [])
            total = len(items)
            free = sum(1 for x in items if x.status == "free")
            rate = free / total if total else None
            row.append({
                "weekday": weekday,
                "hour": hour,
                "total": total,
                "free": free,
                "rate": round(rate, 3) if rate is not None else None,
                # 1/sqrt(n) 近似的 95% 置信半宽
                "ci": round(1.96 * math.sqrt(max(rate * (1 - rate), 1e-6) / total), 3) if total else None,
            })
        matrix.append(row)

    best_slot = None
    for row in matrix:
        for cell in row:
            if cell["rate"] is not None and cell["total"] >= MIN_SAMPLES:
                if best_slot is None or cell["rate"] > best_slot["rate"]:
                    best_slot = cell

    return {
        "building": building,
        "room_no": room_no,
        "name": f"{building} {room_no}",
        "samples": len(logs),
        "enough_data": len(logs) >= MIN_SAMPLES * 4,
        "hours": WORK_HOURS,
        "matrix": matrix,
        "best_slot": best_slot,
        "avg_rate": round(sum(x["rate"] for row in matrix for x in row if x["rate"] is not None)
                          / max(1, sum(1 for row in matrix for x in row if x["rate"] is not None)), 3),
    }


# ─────────── 课程占用惩罚 ───────────
def _busy_locations(db: Session, user_id: int | None, weekday: int, hour: int) -> list[str]:
    """指定 weekday×hour 被课程占用的教室地点列表（user_id=None 表示全校）。"""
    hour_start, hour_end = f"{hour:02d}:00", f"{hour + 1:02d}:00"
    query = (db.query(CourseSchedule, Course)
             .join(Course, CourseSchedule.course_id == Course.id)
             .filter(CourseSchedule.weekday == weekday))
    if user_id:
        query = query.filter(Course.user_id == user_id)
    locations = []
    for slot, course in query.all():
        if not ranges_overlap(slot.start_time, slot.end_time, hour_start, hour_end):
            continue
        loc = (slot.location or course.location or "").strip()
        if loc:
            locations.append(loc)
    return locations


def _room_in_locations(room_no: str, locations: list[str]) -> bool:
    """教室号是否出现在地点串中（边界匹配，避免 201 误配 1201）。"""
    if not room_no:
        return False
    pattern = re.compile(rf"(?<!\d){re.escape(room_no)}(?!\d)")
    return any(pattern.search(loc or "") for loc in locations)


def _match_schedule_room(building: str, room_no: str, location: str, all_buildings: list[str]) -> bool:
    """排课地点是否指向某教室：优先用完整教室号（1#308），失败时退化为
    「教学楼名命中 + 教室数字号边界命中」，以兼容「信东314」这类无 # 的写法。"""
    if _room_in_locations(room_no, [location]):
        return True
    num = room_no.split("#")[-1]
    if not num.isdigit():
        return False
    cands = [b for b in all_buildings if b and b in location]
    if not cands or max(cands, key=len) != building:
        return False
    return re.search(rf"(?<!\d){re.escape(num)}(?!\d)", location) is not None


def _schedule_busy_map(db: Session, user_id: int | None = None) -> tuple[dict, set]:
    """教室课表占用：返回 (busy, known_rooms)。

    busy: (building, room_no) -> {(weekday, hour)} 有课时段
    known_rooms: 导入过课表的教室集合（这些教室无课的时段视为"空闲/绿"，
                 未导入课表的教室保持"未知/灰"）。
    只统计 source=classroom 的教室课表与 PDF 课表；个人课表不影响全校热力图。"""
    sem = db.query(Semester).filter(Semester.is_current.is_(True)).first()
    week = current_week(sem.start_date) if sem and sem.start_date else None
    total = sem.total_weeks if sem else 20

    items: list[tuple[int, str, str, str, str]] = []
    sched_q = (db.query(CourseSchedule)
               .join(Course, CourseSchedule.course_id == Course.id)
               .filter(Course.source == "classroom"))
    if user_id:
        sched_q = sched_q.filter(Course.user_id == user_id)
    for slot in sched_q.all():
        loc = (slot.location or "").strip()
        if loc:
            items.append((slot.weekday, slot.start_time, slot.end_time, loc, slot.weeks or ""))
    pdf_q = db.query(PdfScheduleEntry)
    if user_id:
        pdf_q = (pdf_q.join(PdfScheduleUpload, PdfScheduleEntry.upload_id == PdfScheduleUpload.id)
                 .filter(PdfScheduleUpload.user_id == user_id))
    for e in pdf_q.all():
        loc = (e.location or e.room_no or "").strip()
        if loc:
            items.append((e.weekday, e.start_time, e.end_time, loc, e.weeks or ""))
    if not items:
        return {}, set()

    all_buildings = [b for (b,) in db.query(Classroom.building).distinct().all()]
    rooms_by_building: dict[str, list[str]] = defaultdict(list)
    for building, room_no in db.query(Classroom.building, Classroom.room_no).filter(
            Classroom.is_active.is_(True)).all():  # noqa: E712
        rooms_by_building[building].append(room_no)

    busy: dict[tuple[str, str], set] = defaultdict(set)
    known: set = set()
    for weekday, start, end, loc, weeks in items:
        cands = [b for b in all_buildings if b and b in loc]
        if not cands:
            continue
        building = max(cands, key=len)
        matched = [r for r in rooms_by_building[building]
                   if _match_schedule_room(building, r, loc, all_buildings)]
        if not matched:
            continue
        # 该教室排过课 → 进入"已知"集合（无论本周是否有课）
        for r in matched:
            known.add((building, r))
        if week is not None and weeks and week not in parse_weeks(weeks, total):
            continue
        hours = [h for h in WORK_HOURS if ranges_overlap(start, end, f"{h:02d}:00", f"{h + 1:02d}:00")]
        for r in matched:
            for hour in hours:
                busy[(building, r)].add((weekday, hour))
    return busy, known


def predict(db: Session, user_id: int, *, weekday: int | None = None, hour: int | None = None,
            days_back: int = 90, limit: int = 10) -> dict:
    """空闲预测：个人历史空闲率（时间衰减加权）+ 课程占用惩罚 → 0~100 置信分。"""
    now = datetime.now()
    weekday = weekday or weekday_of()
    hour = hour if hour is not None else now.hour

    since = now - timedelta(days=days_back)
    logs = (db.query(ClassroomStatusLog)
            .filter(ClassroomStatusLog.recorded_at >= since,
                    ClassroomStatusLog.weekday == weekday,
                    ClassroomStatusLog.user_id == user_id)
            .all())
    if not logs:
        return {"weekday": weekday, "hour": hour, "results": [],
                "hint": "该时段暂无历史快照，请先用小程序/接口上报教室状态"}

    self_busy = _busy_locations(db, user_id, weekday, hour)
    all_busy = _busy_locations(db, None, weekday, hour)

    buckets: dict[tuple[str, str], list[ClassroomStatusLog]] = defaultdict(list)
    for log in logs:
        buckets[(log.building, log.room_no)].append(log)

    results = []
    for (building, room_no), items in buckets.items():
        if len(items) < MIN_SAMPLES:
            continue
        if _room_in_locations(room_no, self_busy):
            continue                                  # 自己这节要去这里上课

        weighted_free = weighted_total = 0.0
        for log in items:
            if abs(log.hour - hour) > 1:
                continue
            decay = math.exp(-0.05 * max((now - log.recorded_at).days, 0))
            weight = decay * (1.0 if log.hour == hour else 0.6)
            weighted_total += weight
            if log.status == "free":
                weighted_free += weight
        if weighted_total <= 0:
            continue

        score = weighted_free / weighted_total
        penalty = 0.0
        if _room_in_locations(room_no, all_busy):
            penalty += 0.3                            # 被任意课程点名占用
        latest = max(items, key=lambda x: x.recorded_at)
        confidence = max(0.0, min(1.0, score - penalty))

        results.append({
            "building": building,
            "room_no": room_no,
            "name": f"{building} {room_no}",
            "confidence": round(confidence * 100),
            "free_rate": round(score, 3),
            "samples": len(items),
            "penalty": round(penalty, 2),
            "last_status": latest.status,
            "last_recorded_at": latest.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
            "avg_confidence": round(sum(x.confidence or 0 for x in items) / len(items), 3),
        })

    results.sort(key=lambda x: -x["confidence"])
    return {
        "weekday": weekday,
        "hour": hour,
        "results": results[:limit],
        "hint": None if results else "历史样本不足，请继续采集后获得更准预测",
    }


def building_overview(db: Session) -> list[dict]:
    """各教学楼教室数、样本量、平均空闲率。"""
    rooms = db.query(Classroom).all()
    overview: dict[str, dict] = {}
    for room in rooms:
        item = overview.setdefault(room.building, {"building": room.building, "rooms": 0,
                                                   "samples": 0, "free": 0, "total": 0})
        item["rooms"] += 1
    since = datetime.now() - timedelta(days=120)
    rows = (db.query(ClassroomStatusLog.building, ClassroomStatusLog.status,
                     ClassroomStatusLog.id)
            .filter(ClassroomStatusLog.recorded_at >= since).all())
    for building, status, _ in rows:
        item = overview.setdefault(building, {"building": building, "rooms": 0,
                                              "samples": 0, "free": 0, "total": 0})
        item["samples"] += 1
        item["total"] += 1
        if status == "free":
            item["free"] += 1
    for item in overview.values():
        item["free_rate"] = round(item["free"] / item["total"], 3) if item["total"] else None
    return sorted(overview.values(), key=lambda x: x["building"])


# ─────────── 多模态识图 ───────────
async def recognize_image_async(db: Session, user_id: int, payload) -> dict:
    """调用 deepseek-vl 识别教室状态（路由 await 调用），解析 JSON 并可选落库。"""
    raw = payload.image_base64 or ""
    if len(raw) < 32:
        from app.core.exceptions import AppError

        raise AppError("image_base64 内容过短，请确认已传入图片数据")

    text = await deepseek.vision(raw)
    result = _parse_vision_text(text) or {
        "status": "unknown", "occupied_ratio": 0.0, "confidence": 0.3,
        "seats_visible": 0, "occupied_seats": 0, "reason": "模型返回无法解析",
    }

    log_id = None
    if payload.save_log and payload.building and payload.room_no:
        room = get_or_create_classroom(db, payload.building, payload.room_no)
        log = ClassroomStatusLog(
            classroom_id=room.id, user_id=user_id, building=payload.building,
            room_no=payload.room_no, status=result["status"],
            occupied_seats=int(result.get("occupied_seats") or 0),
            source="ai_vision", confidence=float(result.get("confidence") or 0.5),
            note=payload.note or result.get("reason"),
            recorded_at=datetime.now(), weekday=weekday_of(), hour=datetime.now().hour,
        )
        db.add(log)
        db.commit()
        db.refresh(log)
        log_id = log.id

    return {"recognition": result, "mode": "live" if deepseek.is_configured else "mock",
            "log_id": log_id, "saved": log_id is not None}


def _parse_vision_text(text: str | None) -> dict | None:
    if not text:
        return None
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?|```$", "", cleaned, flags=re.MULTILINE).strip()
    match = re.search(r"\{.*\}", cleaned, flags=re.S)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    status = str(data.get("status", "unknown")).lower()
    if status not in {"free", "busy", "unknown"}:
        status = "unknown"
    return {
        "status": status,
        "occupied_ratio": float(data.get("occupied_ratio") or 0),
        "confidence": float(data.get("confidence") or 0.5),
        "seats_visible": int(data.get("seats_visible") or 0),
        "occupied_seats": int(data.get("occupied_seats") or 0),
        "reason": str(data.get("reason") or "")[:120],
    }


def today_stats(db: Session) -> dict:
    """今日采集概况（供仪表盘使用）。"""
    start = datetime.combine(date.today(), datetime.min.time())
    logs = (db.query(ClassroomStatusLog)
            .filter(ClassroomStatusLog.recorded_at >= start).all())
    free = sum(1 for x in logs if x.status == "free")
    return {
        "date": date.today().isoformat(),
        "reports": len(logs),
        "free": free,
        "busy": sum(1 for x in logs if x.status == "busy"),
        "free_rate": round(free / len(logs), 3) if logs else None,
        "rooms": len({(x.building, x.room_no) for x in logs}),
        "sources": sorted({x.source for x in logs}),
    }


# ═══════════════ 教室使用记录（Excel 导入 · 防重复录入）═══════════════
USAGE_ALIAS = {
    "教室编号": "room_no", "教室": "room_no", "room": "room_no", "room_no": "room_no",
    "教学楼": "building", "楼栋": "building", "building": "building",
    "日期": "use_date", "使用日期": "use_date", "date": "use_date",
    "时间段": "slot", "时间": "slot", "时段": "slot",
    "开始时间": "start_time", "开始": "start_time", "start": "start_time",
    "结束时间": "end_time", "结束": "end_time", "end": "end_time",
    "使用状态": "status", "状态": "status", "status": "status",
    "上次使用部门": "department", "使用部门": "department", "部门": "department", "department": "department",
    "用途": "purpose", "使用用途": "purpose", "purpose": "purpose",
    "备注": "note", "note": "note",
}
STATUS_MAP = {"空闲": "free", "free": "free", "使用": "busy", "占用": "busy", "busy": "busy"}


def _norm_room_no(raw: str) -> str:
    """归一化教室编号：`10教 10#101` / `10#101` / `10-1#101` → `10#101`。"""
    s = re.sub(r"\s+", "", str(raw or ""))
    m = re.search(r"(\d+#\d+)$", s)
    return m.group(1) if m else s


def _parse_slot(cell) -> tuple[str, str] | None:
    """解析时间段单元格：`08:00-09:40` / `8:00~9:40` / datetime 对。"""
    s = str(cell or "").strip()
    m = re.match(r"^(\d{1,2}[:：]\d{2})\s*[-–—~至]+\s*(\d{1,2}[:：]\d{2})$", s)
    if m:
        return m.group(1).replace("：", ":"), m.group(2).replace("：", ":")
    return None


def _parse_date(cell) -> date | None:
    if isinstance(cell, datetime):
        return cell.date()
    if isinstance(cell, date):
        return cell
    s = str(cell or "").strip()
    m = re.match(r"^(\d{4})[-/年.](\d{1,2})[-/月.](\d{1,2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _fix_hhmm(v: str) -> str | None:
    m = re.match(r"^(\d{1,2})[:：](\d{2})$", str(v or "").strip())
    if not m:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def parse_usage_excel(data: bytes) -> list[dict]:
    """解析教室使用信息 Excel：需含表头行（教室编号/日期/时间段/使用状态/使用部门/用途…）。"""
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover
        raise AppError("服务端未安装 openpyxl，无法解析 Excel")
    wb = load_workbook(io.BytesIO(data), data_only=True)
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise AppError("Excel 内容为空")

    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    colmap: dict[int, str] = {}
    for idx, name in enumerate(header):
        key = USAGE_ALIAS.get(name.lower()) or USAGE_ALIAS.get(name)
        if key:
            colmap[idx] = key
    if "room_no" not in colmap.values() or "use_date" not in colmap.values():
        raise AppError("Excel 缺少必需列：教室编号、日期（请参照模板：教室编号/日期/时间段/使用状态/使用部门/用途）")

    records: list[dict] = []
    for line_no, raw in enumerate(rows[1:], start=2):
        if not raw or all(c is None or str(c).strip() == "" for c in raw):
            continue
        rec: dict = {}
        for idx, key in colmap.items():
            rec[key] = raw[idx] if idx < len(raw) else None
        room_no = _norm_room_no(rec.get("room_no"))
        if not room_no:
            records.append({"_error": f"第 {line_no} 行：教室编号为空", "_line": line_no})
            continue
        d = _parse_date(rec.get("use_date"))
        if d is None:
            records.append({"_error": f"第 {line_no} 行：日期无法识别（支持 2026-10-02 / 2026/10/2）", "_line": line_no})
            continue
        # 时间段：优先「时间段」列，否则开始/结束时间列
        slot = _parse_slot(rec.get("slot"))
        if not slot:
            s1, s2 = _fix_hhmm(rec.get("start_time")), _fix_hhmm(rec.get("end_time"))
            slot = (s1, s2) if s1 and s2 else None
        else:
            slot = (_fix_hhmm(slot[0]), _fix_hhmm(slot[1]))
        if not slot:
            records.append({"_error": f"第 {line_no} 行：时间段无法识别（支持 08:00-09:40 或开始/结束时间列）", "_line": line_no})
            continue
        if to_minutes(slot[0]) >= to_minutes(slot[1]):
            records.append({"_error": f"第 {line_no} 行：开始时间必须早于结束时间", "_line": line_no})
            continue
        status = STATUS_MAP.get(str(rec.get("status") or "").strip().lower(), "busy")
        records.append({
            "building": str(rec.get("building") or "").strip() or None,
            "room_no": room_no, "use_date": d,
            "start_time": slot[0], "end_time": slot[1],
            "status": status,
            "department": str(rec.get("department") or "").strip() or None,
            "purpose": str(rec.get("purpose") or "").strip() or None,
            "note": str(rec.get("note") or "").strip() or None,
            "_line": line_no,
        })
    if not records:
        raise AppError("Excel 中没有有效的数据行")
    return records


def _match_room(db: Session, building: str | None, room_no: str) -> Classroom | None:
    """按教室编号在教室表中定位（优先带楼名精确匹配，再退回编号后缀匹配）。"""
    if building:
        room = (db.query(Classroom)
                .filter(Classroom.building == building, Classroom.room_no == room_no).first())
        if room:
            return room
    room = db.query(Classroom).filter(Classroom.room_no == room_no).first()
    if room:
        return room
    return (db.query(Classroom)
            .filter(Classroom.room_no.like(f"%{room_no}")).first())


def import_usage_records(db: Session, data: bytes, user_id: int | None = None) -> dict:
    """导入使用记录 Excel，防重复录入：
    ① 文件内同一教室同一天时间段重叠 → 跳过并报错；
    ② 库内已有相同/时间段重叠记录 → 跳过并提示冲突详情。
    成功导入的记录同步写入状态日志，联动教室热力图。"""
    rows = parse_usage_excel(data)
    created, skipped, errors = [], [], []

    # 文件内查重
    seen: list[dict] = []
    valid: list[dict] = []
    for r in rows:
        if "_error" in r:
            errors.append({"line": r["_line"], "reason": r["_error"]})
            continue
        dup = next((s for s in seen if s["room_no"] == r["room_no"] and s["use_date"] == r["use_date"]
                    and ranges_overlap(s["start_time"], s["end_time"], r["start_time"], r["end_time"])), None)
        if dup:
            errors.append({"line": r["_line"],
                           "reason": f"文件内重复：第 {dup['_line']} 行已录入 {r['room_no']} "
                                     f"{r['use_date']} {dup['start_time']}-{dup['end_time']}，时间段重叠"})
            continue
        seen.append(r)
        valid.append(r)

    for r in valid:
        room = _match_room(db, r.get("building"), r["room_no"])
        building = room.building if room else (r.get("building") or "未知楼")
        # 库内查重（同教室同日时间段重叠）
        existing = (db.query(ClassroomUsageRecord)
                    .filter(ClassroomUsageRecord.building == building,
                            ClassroomUsageRecord.room_no == (room.room_no if room else r["room_no"]),
                            ClassroomUsageRecord.use_date == r["use_date"]).all())
        conflict = next((x for x in existing
                         if ranges_overlap(x.start_time, x.end_time, r["start_time"], r["end_time"])), None)
        if conflict:
            skipped.append({"room": f"{building} {r['room_no']}", "line": r["_line"],
                            "reason": f"该时间段已录入（{conflict.start_time}-{conflict.end_time} "
                                      f"{conflict.department or ''}{conflict.purpose or ''}），重复录入已阻止"})
            continue

        rec = ClassroomUsageRecord(
            classroom_id=room.id if room else None, building=building,
            room_no=room.room_no if room else r["room_no"],
            use_date=r["use_date"], start_time=r["start_time"], end_time=r["end_time"],
            status=r["status"], department=r["department"], purpose=r["purpose"],
            note=r["note"], source="excel",
        )
        db.add(rec)
        db.flush()
        # 联动热力图：按小时段写状态日志（free 记录同样落库）
        room_no_final = rec.room_no
        h0 = int(r["start_time"][:2])
        h1 = int(r["end_time"][:2])
        for hour in range(h0, min(h1 + (1 if r["end_time"][3:] != "00" else 0), 24)):
            db.add(ClassroomStatusLog(
                classroom_id=room.id if room else None, user_id=user_id,
                building=building, room_no=room_no_final, status=r["status"],
                source="excel", confidence=1.0,
                note=f"{r['department'] or ''} {r['purpose'] or ''}".strip() or None,
                recorded_at=datetime.combine(r["use_date"], datetime.min.time()).replace(hour=hour),
                weekday=r["use_date"].isoweekday(), hour=hour,
            ))
        created.append({"id": rec.id, "room": f"{building} {room_no_final}",
                        "slot": f"{r['use_date']} {r['start_time']}-{r['end_time']}"})
    db.commit()
    return {"created": len(created), "skipped": len(skipped), "errors": len(errors),
            "created_items": created, "skipped_items": skipped, "error_items": errors}


def _classify_course(name: str) -> str:
    if any(k in name for k in ("实验", "实训", "实习", "上机")):
        return "实验课"
    if "体育" in name:
        return "体育课"
    if any(k in name for k in ("设计", "制作", "训练")):
        return "实践课"
    return "理论课"


def _room_courses(db: Session, building: str, room_no: str,
                  weekday: int, at: str, day: date) -> list[dict]:
    """该教室在 weekday×时刻 的课程安排：PDF 课表条目 + 课程表（Course）双来源合并。"""
    hour_end = f"{int(at[:2]) + 1:02d}:00"
    out: list[dict] = []
    seen: set[tuple] = set()

    # 来源①：PDF 教室课表解析条目（含班级信息）
    sem = db.query(Semester).filter(Semester.is_current.is_(True)).first()
    week = current_week(sem.start_date, day) if sem and sem.start_date else None
    total = sem.total_weeks if sem else 20
    all_buildings = [b for (b,) in db.query(Classroom.building).distinct().all()]
    q = (db.query(PdfScheduleEntry, PdfScheduleUpload.filename)
         .join(PdfScheduleUpload, PdfScheduleEntry.upload_id == PdfScheduleUpload.id)
         .filter(PdfScheduleEntry.weekday == weekday))
    for e, filename in q.all():
        if not _match_schedule_room(building, room_no, e.location or e.room_no or "", all_buildings):
            continue
        if not ranges_overlap(e.start_time, e.end_time, at, hour_end):
            continue
        if week and week not in parse_weeks(e.weeks, total):
            continue
        key = (e.course_name, e.start_time, e.end_time)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "source": "pdf", "course_name": e.course_name, "teacher": e.teacher,
            "class_name": e.class_name, "start_time": e.start_time, "end_time": e.end_time,
            "weeks": e.weeks, "week_type": e.week_type,
            "course_type": _classify_course(e.course_name),
            "location": e.location or f"{building} {room_no}", "detail": filename,
        })

    # 来源②：课程表（本人导入的课，按地点匹配教室号）
    q2 = (db.query(CourseSchedule, Course)
          .join(Course, CourseSchedule.course_id == Course.id)
          .filter(CourseSchedule.weekday == weekday))
    for slot, course in q2.all():
        loc = (slot.location or course.location or "").strip()
        if not loc or not _match_schedule_room(building, room_no, loc, all_buildings):
            continue
        if not ranges_overlap(slot.start_time, slot.end_time, at, hour_end):
            continue
        key = (course.name, slot.start_time, slot.end_time)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "source": "course", "course_name": course.name, "teacher": course.teacher,
            "class_name": course.note, "start_time": slot.start_time, "end_time": slot.end_time,
            "weeks": slot.weeks, "week_type": slot.week_type,
            "course_type": _classify_course(course.name),
            "location": loc, "detail": course.name,
        })
    out.sort(key=lambda x: x["start_time"])
    return out


def room_usage_at(db: Session, building: str, room_no: str,
                  day: date | None = None, hour: int | None = None) -> dict:
    """某教室在指定时段的使用详情：课程安排 + 当前时段记录 + 上次使用（供点击格子弹窗）。"""
    day = day or date.today()
    now = datetime.now()
    if hour is None and day == now.date():
        at = f"{now.hour:02d}:{now.minute:02d}"
    else:
        at = f"{(hour if hour is not None else 8):02d}:00"
    weekday = day.isoweekday()
    courses = _room_courses(db, building, room_no, weekday, at, day)

    def _covers(rec: ClassroomUsageRecord) -> bool:
        return rec.use_date == day and rec.start_time <= at < rec.end_time

    day_recs = (db.query(ClassroomUsageRecord)
                .filter(ClassroomUsageRecord.building == building,
                        ClassroomUsageRecord.room_no == room_no,
                        ClassroomUsageRecord.use_date == day)
                .order_by(ClassroomUsageRecord.start_time).all())
    current = next((r for r in day_recs if _covers(r)), None)

    # 上次使用：早于当前时段（或早于今天）的最近一条 busy 记录
    prev_q = (db.query(ClassroomUsageRecord)
              .filter(ClassroomUsageRecord.building == building,
                      ClassroomUsageRecord.room_no == room_no,
                      ClassroomUsageRecord.status == "busy"))
    if current:
        prev = prev_q.filter(
            (ClassroomUsageRecord.use_date < day) |
            ((ClassroomUsageRecord.use_date == day) & (ClassroomUsageRecord.end_time <= current.start_time))
        ).order_by(ClassroomUsageRecord.use_date.desc(), ClassroomUsageRecord.end_time.desc()).first()
    else:
        prev = prev_q.filter(ClassroomUsageRecord.use_date < day).order_by(
            ClassroomUsageRecord.use_date.desc(), ClassroomUsageRecord.end_time.desc()).first()

    # 无 Excel 记录时回退到状态日志（拍照上报等），保证弹窗总有信息可展示
    fallback = None
    if current is None and prev is None:
        logs = (db.query(ClassroomStatusLog)
                .filter(ClassroomStatusLog.building == building,
                        ClassroomStatusLog.room_no == room_no,
                        ClassroomStatusLog.recorded_at >= datetime.combine(day - timedelta(days=30),
                                                                           datetime.min.time()))
                .order_by(ClassroomStatusLog.recorded_at.desc()).limit(10).all())
        fallback = [x.to_dict() for x in logs]

    return {
        "building": building, "room_no": room_no,
        "day": day.isoformat(), "at": at,
        "courses": courses,
        "current": current.to_dict() if current else None,
        "previous": prev.to_dict() if prev else None,
        "day_records": [r.to_dict() for r in day_recs],
        "recent_logs": fallback or [],
    }
