"""课程服务：冲突检测、批量导入、周课表、今日课程。"""
from __future__ import annotations

import io
import re
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import AppError, ConflictError, NotFoundError
from app.models.course import Course, CourseSchedule, Semester
from app.utils.timeutil import (current_week, parse_weeks, ranges_overlap, section_to_time,
                                to_minutes, weeks_intersect, weekday_of)

# ─────────── 学期 ───────────
def list_semesters(db: Session, user_id: int) -> list[Semester]:
    # MySQL 不支持 NULLS LAST，用「空值排最后」的可移植写法
    return (db.query(Semester)
            .filter(Semester.user_id == user_id)
            .order_by(Semester.is_current.desc(),
                      Semester.start_date.is_(None).asc(),
                      Semester.start_date.desc())
            .all())


def ensure_default_semester(db: Session, user_id: int) -> Semester:
    current = db.query(Semester).filter(Semester.user_id == user_id, Semester.is_current.is_(True)).first()
    if current:
        return current
    today = date.today()
    month = today.month
    year = today.year if month >= 8 else today.year - 1
    name = f"{year}-{year + 1} 学年{'第一' if month >= 8 else '第二'}学期"
    sem = Semester(
        user_id=user_id, name=name, total_weeks=20, is_current=True,
        start_date=date(year, 9 if month >= 8 else 2, 1),
    )
    db.add(sem)
    db.commit()
    db.refresh(sem)
    return sem


def set_current_semester(db: Session, user_id: int, semester_id: int) -> Semester:
    sem = db.get(Semester, semester_id)
    if not sem or sem.user_id != user_id:
        raise NotFoundError("学期不存在")
    db.query(Semester).filter(Semester.user_id == user_id).update({"is_current": False})
    sem.is_current = True
    db.commit()
    db.refresh(sem)
    return sem


# ─────────── 冲突检测 ───────────
def _slot_ranges(schedules: list) -> list[dict]:
    out = []
    for s in schedules:
        data = s if isinstance(s, dict) else s.__dict__
        start = data.get("start_time") or section_to_time(data.get("start_section", 1))
        end = data.get("end_time") or section_to_time(data.get("end_section", 2))
        out.append({
            "weekday": int(data["weekday"]),
            "start_time": start,
            "end_time": end,
            "weeks": data.get("weeks") or "1-20",
            "location": data.get("location"),
        })
    return out


def find_conflicts(
    db: Session,
    user_id: int,
    schedules: list,
    *,
    semester_id: int | None = None,
    exclude_course_id: int | None = None,
    total_weeks: int = 20,
) -> list[dict]:
    """同一 weekday + 时间重叠 + 周次相交 → 冲突。"""
    incoming = _slot_ranges(schedules)
    if not incoming:
        return []

    query = (
        db.query(CourseSchedule, Course)
        .join(Course, CourseSchedule.course_id == Course.id)
        # 冲突检测只针对个人课表；教室课表允许同一时段多班级并存
        .filter(Course.user_id == user_id, Course.source == "personal")
    )
    if semester_id:
        query = query.filter(Course.semester_id == semester_id)
    if exclude_course_id:
        query = query.filter(Course.id != exclude_course_id)

    conflicts: list[dict] = []
    for existing, course in query.all():
        for slot in incoming:
            if existing.weekday != slot["weekday"]:
                continue
            if not ranges_overlap(existing.start_time, existing.end_time, slot["start_time"], slot["end_time"]):
                continue
            if not weeks_intersect(existing.weeks, slot["weeks"], total_weeks):
                continue
            conflicts.append({
                "weekday": slot["weekday"],
                "start_time": max(existing.start_time, slot["start_time"], key=to_minutes),
                "end_time": min(existing.end_time, slot["end_time"], key=to_minutes),
                "weeks": f"{slot['weeks']} ∩ {existing.weeks}",
                "course_a": course.name,
                "course_b": "（本次提交）",
                "location_a": existing.location or course.location,
                "location_b": slot.get("location"),
                "reason": "同一天时间重叠且周次相交",
            })
    return conflicts


# ─────────── 课程 CRUD ───────────
def create_course(db: Session, user_id: int, payload, *, force: bool = False,
                  source: str = "personal") -> Course:
    if payload.semester_id:
        sem = db.get(Semester, payload.semester_id)
        if not sem or sem.user_id != user_id:
            raise NotFoundError("学期不存在")
        total_weeks = sem.total_weeks
    else:
        sem = ensure_default_semester(db, user_id)
        total_weeks = sem.total_weeks

    # 教室课表（全校占用数据）不做个人冲突校验：同一时段允许多班级并存
    if source == "personal":
        conflicts = find_conflicts(db, user_id, payload.schedules, semester_id=sem.id,
                                   total_weeks=total_weeks)
        if conflicts and not force:
            raise ConflictError("课程时间与已有安排冲突", detail={"conflicts": conflicts})

    course = Course(
        user_id=user_id,
        semester_id=sem.id,
        name=payload.name,
        teacher=payload.teacher,
        location=payload.location,
        credit=payload.credit,
        course_type=payload.course_type,
        color=payload.color,
        note=payload.note,
        source=source,
    )
    db.add(course)
    db.flush()
    for slot in payload.schedules:
        db.add(CourseSchedule(
            course_id=course.id,
            weekday=slot.weekday,
            start_section=slot.start_section,
            end_section=slot.end_section,
            start_time=slot.start_time,
            end_time=slot.end_time,
            weeks=slot.weeks,
            week_type=slot.week_type,
            location=slot.location or payload.location,
        ))
    db.commit()
    db.refresh(course)
    return course


def update_course(db: Session, user_id: int, course_id: int, payload, *, force: bool = False) -> Course:
    course = get_course(db, user_id, course_id)
    fields = payload.model_dump(exclude_unset=True, exclude={"schedules"})
    for key, value in fields.items():
        if value is not None:
            setattr(course, key, value)

    if payload.schedules is not None:
        conflicts = find_conflicts(db, user_id, payload.schedules,
                                   semester_id=course.semester_id,
                                   exclude_course_id=course.id)
        if conflicts and not force:
            raise ConflictError("课程时间与已有安排冲突", detail={"conflicts": conflicts})
        course.schedules.clear()
        db.flush()
        for slot in payload.schedules:
            db.add(CourseSchedule(
                course_id=course.id,
                weekday=slot.weekday,
                start_section=slot.start_section,
                end_section=slot.end_section,
                start_time=slot.start_time,
                end_time=slot.end_time,
                weeks=slot.weeks,
                week_type=slot.week_type,
                location=slot.location or course.location,
            ))
    db.commit()
    db.refresh(course)
    return course


def get_course(db: Session, user_id: int, course_id: int) -> Course:
    course = db.get(Course, course_id)
    if not course or course.user_id != user_id:
        raise NotFoundError("课程不存在")
    return course


def list_courses(db: Session, user_id: int, *, semester_id: int | None = None,
                 keyword: str | None = None, source: str | None = "personal") -> list[Course]:
    query = db.query(Course).filter(Course.user_id == user_id)
    if source:
        query = query.filter(Course.source == source)
    if semester_id:
        query = query.filter(Course.semester_id == semester_id)
    if keyword:
        query = query.filter(Course.name.like(f"%{keyword}%"))
    return query.order_by(Course.name).all()


def delete_course(db: Session, user_id: int, course_id: int) -> None:
    course = get_course(db, user_id, course_id)
    db.delete(course)
    db.commit()


def import_courses(db: Session, user_id: int, payload, *, source: str = "personal") -> dict:
    """批量导入：先做整体校验，冲突课程可选择跳过（force=True 则全部写入）。

    source: personal=个人课表 | classroom=教室课表（不做冲突校验，replace 只清同类来源）。"""
    created, skipped, conflicts_all = [], [], []
    if payload.replace and payload.semester_id:
        db.query(Course).filter(Course.user_id == user_id,
                                Course.semester_id == payload.semester_id,
                                Course.source == source).delete()
        db.commit()

    for item in payload.courses:
        try:
            course = create_course(db, user_id, item, force=(source != "personal"),
                                   source=source)
            rooms = sorted({(s.location or course.location or "") for s in course.schedules} - {""})
            created.append({"id": course.id, "name": course.name,
                            "teacher": course.teacher, "rooms": rooms})
        except ConflictError as exc:
            conflicts_all.append({"name": item.name, "conflicts": exc.detail.get("conflicts", [])})
            skipped.append(item.name)
    return {
        "created": len(created),
        "skipped": len(skipped),
        "created_items": created,
        "skipped_items": skipped,
        "conflicts": conflicts_all,
    }


CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7,
          "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}


def _parse_grid_block(lines: list[str], wd: int, sec_time: dict) -> tuple | None:
    """解析一个课程格子：行序 课程名/[班级名]/老师*/周次/节次/地点。"""
    weeks, week_type, ss, es = "1-16", "全周", None, None
    others: list[str] = []
    for l in lines:
        mw = re.fullmatch(r"([\d,，\-]+)周(单|双)?", l)
        ms = re.fullmatch(r"(\d+)(?:-(\d+))?节", l)
        if mw:
            weeks = mw.group(1).replace("，", ",")
            week_type = {"单": "单周", "双": "双周"}.get(mw.group(2), "全周")
        elif ms:
            ss = int(ms.group(1))
            es = int(ms.group(2) or ms.group(1))
        else:
            others.append(l)
    if not others:
        return None
    name = others[0]
    teacher = cls = location = None
    for l in others[1:]:
        if teacher is None and l.endswith("*"):
            teacher = l.rstrip("*").strip()
        elif re.search(r"(#|楼|馆|区|校区)", l):
            location = l
        elif "_" in l and cls is None:
            cls = l
    if teacher is None and len(others) > 1 and location != others[1]:
        teacher = others[1].rstrip("*").strip()
    start = sec_time.get(ss, ("08:00", "08:45"))[0] if ss else "08:00"
    end = sec_time.get(es, ("09:40", "09:40"))[1] if es else "09:40"
    return name, teacher, cls, {
        "weekday": wd,
        "start_section": ss or 1,
        "end_section": max(es or 2, ss or 1),
        "start_time": start,
        "end_time": end,
        "weeks": weeks,
        "week_type": week_type,
        "location": location,
    }


def _try_parse_grid(wb) -> list[dict] | None:
    """识别学校官方"网格课表"（星期×节次）；非该格式返回 None。"""
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    header_idx = None
    for i, row in enumerate(rows[:15]):
        if any("星期一" in str(c) for c in row if c is not None):
            header_idx = i
            break
    if header_idx is None:
        return None

    day_cols: dict[int, int] = {}
    for j, c in enumerate(rows[header_idx]):
        s = str(c).strip() if c is not None else ""
        m = re.search(r"星期([一二三四五六日天])", s)
        if m:
            day_cols[j] = CN_NUM[m.group(1)]

    sec_time: dict[int, tuple[str, str]] = {}
    for row in rows:
        for c in row:
            s = str(c).strip() if c is not None else ""
            m = re.search(r"第([一二三四五六七八九十]+)小节\((\d{1,2}:\d{2})-(\d{1,2}:\d{2})\)", s)
            if m and m.group(1) in CN_NUM:
                sec_time[CN_NUM[m.group(1)]] = (m.group(2), m.group(3))

    grouped: dict[tuple, dict] = {}
    for row in rows[header_idx + 1:]:
        first_cell = str(row[0]).strip() if row and row[0] is not None else ""
        if "未安排" in first_cell:
            break  # 网格区结束，后面是课程清单表
        for j, wd in day_cols.items():
            cell = row[j] if j < len(row) else None
            if cell is None or not str(cell).strip():
                continue
            for block in re.split(r"\n\s*\n", str(cell)):
                lines = [l.strip() for l in block.splitlines() if l.strip()]
                if not lines:
                    continue
                parsed = _parse_grid_block(lines, wd, sec_time)
                if not parsed:
                    continue
                name, teacher, cls, sched = parsed
                key = (name, teacher)
                if key not in grouped:
                    grouped[key] = {"name": name, "teacher": teacher, "cls": cls,
                                    "location": sched.get("location"), "schedules": []}
                grouped[key]["schedules"].append(sched)

    out = []
    for c in grouped.values():
        note = f"教学班：{c['cls']}" if c["cls"] else None
        out.append({"name": c["name"], "teacher": c["teacher"], "location": c["location"],
                    "credit": 0.0, "course_type": "必修", "color": "#4ade80", "note": note,
                    "schedules": c["schedules"]})
    return out


def parse_course_excel(data: bytes) -> list[dict]:
    """解析 Excel：自动识别两种格式——
    ① 学校官方网格课表（星期×节次，单元格含 课程名/老师/周次/节次/地点）
    ② 平铺表（列名 课程名/老师/教室/星期/开始/结束/周次/学分）。"""
    try:
        from openpyxl import load_workbook
    except ImportError:  # pragma: no cover
        raise AppError("服务端未安装 openpyxl，无法解析 Excel")
    wb = load_workbook(io.BytesIO(data), data_only=True)

    grid = _try_parse_grid(wb)
    if grid:
        return grid

    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        raise AppError("Excel 内容为空")

    header = [str(c).strip() if c is not None else "" for c in rows[0]]
    alias = {
        "课程名": "name", "课程": "name", "name": "name",
        "老师": "teacher", "教师": "teacher", "teacher": "teacher",
        "教室": "location", "地点": "location", "location": "location",
        "星期": "weekday", "周几": "weekday", "weekday": "weekday",
        "开始": "start_time", "开始时间": "start_time", "start": "start_time",
        "结束": "end_time", "结束时间": "end_time", "end": "end_time",
        "周次": "weeks", "weeks": "weeks",
        "学分": "credit", "credit": "credit",
        "备注": "note", "note": "note",
    }
    week_map = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}

    courses: list[dict] = []
    for raw in rows[1:]:
        if not raw or all(c is None or str(c).strip() == "" for c in raw):
            continue
        record: dict = {}
        for idx, cell in enumerate(raw):
            if idx >= len(header):
                break
            key = alias.get(header[idx])
            if not key:
                continue
            value = cell
            if key == "weekday":
                text = str(value).strip().replace("周", "")
                value = week_map.get(text[-1:], None) or (int(text) if text.isdigit() else 1)
            elif key in {"start_time", "end_time"}:
                value = _normalize_time(value)
            elif key == "credit":
                try:
                    value = float(value or 0)
                except (TypeError, ValueError):
                    value = 0.0
            record[key] = value
        if not record.get("name"):
            continue

        start = record.get("start_time") or "08:00"
        courses.append({
            "name": str(record["name"]).strip(),
            "teacher": record.get("teacher"),
            "location": record.get("location"),
            "credit": record.get("credit") or 0.0,
            "note": record.get("note"),
            "schedules": [{
                "weekday": int(record.get("weekday") or 1),
                "start_time": start,
                "end_time": record.get("end_time") or _add_minutes(start, 100),
                "weeks": str(record.get("weeks") or "1-16"),
                "week_type": "全周",
                "location": record.get("location"),
            }],
        })
    return courses


def _normalize_time(value) -> str:
    if value is None:
        return "08:00"
    if isinstance(value, datetime):
        return value.strftime("%H:%M")
    text = str(value).strip().replace("：", ":")
    if ":" in text:
        hh, mm = text.split(":", 1)
        return f"{int(hh):02d}:{int(mm[:2]):02d}"
    if text.isdigit() and len(text) in (3, 4):
        return f"{int(text[:-2]):02d}:{int(text[-2:]):02d}"
    return "08:00"


def _add_minutes(hhmm: str, minutes: int) -> str:
    total = to_minutes(hhmm) + minutes
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


# ─────────── 课表视图 ───────────
def week_timetable(db: Session, user_id: int, week: int | None = None,
                   semester_id: int | None = None) -> dict:
    sem = (db.get(Semester, semester_id) if semester_id
           else db.query(Semester).filter(Semester.user_id == user_id,
                                          Semester.is_current.is_(True)).first())
    total_weeks = sem.total_weeks if sem else 20
    week = week or (current_week(sem.start_date) if sem and sem.start_date else 1)

    courses = list_courses(db, user_id, semester_id=sem.id if sem else None)
    days = []
    for weekday in range(1, 8):
        slots = []
        for course in courses:
            for s in course.schedules:
                if s.weekday != weekday:
                    continue
                if week not in parse_weeks(s.weeks, total_weeks):
                    continue
                slots.append({
                    "course_id": course.id,
                    "name": course.name,
                    "teacher": course.teacher,
                    "location": s.location or course.location,
                    "color": course.color,
                    "weekday": weekday,
                    "start_time": s.start_time,
                    "end_time": s.end_time,
                    "start_section": s.start_section,
                    "end_section": s.end_section,
                    "weeks": s.weeks,
                })
        slots.sort(key=lambda x: to_minutes(x["start_time"]))
        days.append({"weekday": weekday, "classes": slots})
    return {
        "semester": sem.to_dict() if sem else None,
        "week": week,
        "total_weeks": total_weeks,
        "total_classes": sum(len(d["classes"]) for d in days),
        "days": days,
    }


def today_classes(db: Session, user_id: int, *, target: date | None = None) -> list[dict]:
    target = target or date.today()
    weekday = weekday_of(target)
    timetable = week_timetable(db, user_id)
    now = datetime.now().strftime("%H:%M")
    result = []
    for day in timetable["days"]:
        if day["weekday"] != weekday:
            continue
        for slot in day["classes"]:
            if slot["end_time"] <= now and target == date.today():
                status = "done"
            elif slot["start_time"] <= now < slot["end_time"] and target == date.today():
                status = "current"
            else:
                status = "upcoming"
            result.append({**slot, "date": target.isoformat(), "status": status,
                           "class_status": status})
    return result
