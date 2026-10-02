"""健康服务：记录（按日 upsert）、报告、久坐心跳与打断。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models.health import HealthRecord, HealthSetting
from app.utils.timeutil import to_minutes


def get_or_create_settings(db: Session, user_id: int) -> HealthSetting:
    setting = db.query(HealthSetting).filter(HealthSetting.user_id == user_id).first()
    if setting:
        return setting
    setting = HealthSetting(user_id=user_id, last_heartbeat_at=datetime.now())
    db.add(setting)
    db.commit()
    db.refresh(setting)
    return setting


def update_settings(db: Session, user_id: int, payload) -> HealthSetting:
    setting = get_or_create_settings(db, user_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(setting, key, value)
    db.commit()
    db.refresh(setting)
    return setting


def get_record(db: Session, user_id: int, record_id: int) -> HealthRecord:
    record = db.get(HealthRecord, record_id)
    if not record or record.user_id != user_id:
        raise NotFoundError("健康记录不存在")
    return record


def upsert_record(db: Session, user_id: int, payload) -> HealthRecord:
    """按日期 upsert：同一天重复提交为累加/覆盖，避免重复行。"""
    target = payload.date or date.today()
    record = (db.query(HealthRecord)
              .filter(HealthRecord.user_id == user_id, HealthRecord.date == target).first())
    if not record:
        record = HealthRecord(user_id=user_id, date=target)
        db.add(record)
    for key, value in payload.model_dump(exclude_unset=True, exclude={"date"}).items():
        if value is None:
            continue
        if key in {"exercise_minutes", "water_ml", "steps"} and getattr(record, key, 0):
            setattr(record, key, (getattr(record, key) or 0) + value)   # 累计型字段叠加
        else:
            setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


def update_record(db: Session, user_id: int, record_id: int, payload) -> HealthRecord:
    record = get_record(db, user_id, record_id)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record


def delete_record(db: Session, user_id: int, record_id: int) -> None:
    record = get_record(db, user_id, record_id)
    db.delete(record)
    db.commit()


def list_records(db: Session, user_id: int, *, days: int = 7) -> list[HealthRecord]:
    start = date.today() - timedelta(days=days - 1)
    return (db.query(HealthRecord)
            .filter(HealthRecord.user_id == user_id, HealthRecord.date >= start)
            .order_by(HealthRecord.date).all())


def sedentary_status(db: Session, user_id: int, *, touch: bool = False) -> dict:
    """久坐状态：距上次起身的分钟数、是否提醒、是否处于免打扰时段。"""
    setting = get_or_create_settings(db, user_id)
    now = datetime.now()
    base = setting.last_heartbeat_at or now
    minutes = int((now - base).total_seconds() // 60)
    if touch:
        setting.last_heartbeat_at = now
        db.commit()

    in_quiet = False
    if setting.quiet_start and setting.quiet_end:
        start, end = to_minutes(setting.quiet_start), to_minutes(setting.quiet_end)
        current = now.hour * 60 + now.minute
        in_quiet = start <= current <= end if start <= end else (current >= start or current <= end)

    in_active = True
    if setting.active_start and setting.active_end:
        start, end = to_minutes(setting.active_start), to_minutes(setting.active_end)
        current = now.hour * 60 + now.minute
        in_active = start <= current <= end

    should_break = bool(setting.sedentary_enabled and minutes >= setting.sedentary_interval_min
                        and not in_quiet and in_active)
    return {
        "minutes_since_break": minutes,
        "interval_min": setting.sedentary_interval_min,
        "enabled": setting.sedentary_enabled,
        "should_break": should_break,
        "in_quiet_hours": in_quiet,
        "in_active_hours": in_active,
        "last_heartbeat_at": setting.last_heartbeat_at.strftime("%Y-%m-%d %H:%M:%S") if setting.last_heartbeat_at else None,
        "message": (f"已连续久坐 {minutes} 分钟，建议起身活动 5 分钟"
                    if should_break else f"久坐计时 {minutes} 分钟，状态良好"),
    }


def heartbeat(db: Session, user_id: int, spent_minutes: int = 0) -> dict:
    """前端心跳：累加久坐时长（写回 last_heartbeat_at 作为计时基准）。"""
    setting = get_or_create_settings(db, user_id)
    now = datetime.now()
    if setting.last_heartbeat_at is None:
        setting.last_heartbeat_at = now
    db.commit()
    return sedentary_status(db, user_id)


def take_break(db: Session, user_id: int, *, note: str | None = None) -> dict:
    """已起身：重置计时并累计到今日健康记录。"""
    setting = get_or_create_settings(db, user_id)
    break_minutes = int((datetime.now() - (setting.last_heartbeat_at or datetime.now()))
                        .total_seconds() // 60)
    setting.last_heartbeat_at = datetime.now()
    db.commit()

    today = date.today()
    record = (db.query(HealthRecord)
              .filter(HealthRecord.user_id == user_id, HealthRecord.date == today).first())
    if not record:
        record = HealthRecord(user_id=user_id, date=today)
        db.add(record)
    record.sedentary_minutes = (record.sedentary_minutes or 0) + max(0, break_minutes)
    if note:
        record.note = (record.note + " | " if record.note else "") + note
    db.commit()
    return {"break_minutes": break_minutes, **sedentary_status(db, user_id)}


def report(db: Session, user_id: int, days: int = 7) -> dict:
    """健康报告：日均睡眠/运动/久坐、体重变化、达标率与建议。"""
    setting = get_or_create_settings(db, user_id)
    records = list_records(db, user_id, days=days)
    by_date = {r.date.isoformat(): r for r in records}

    daily = []
    for i in range(days - 1, -1, -1):
        day = date.today() - timedelta(days=i)
        record = by_date.get(day.isoformat())
        daily.append({
            "date": day.isoformat(),
            "sleep_hours": round((record.sleep_minutes or 0) / 60, 2) if record else 0,
            "exercise_minutes": record.exercise_minutes if record else 0,
            "sedentary_minutes": record.sedentary_minutes if record else 0,
            "water_ml": record.water_ml if record else 0,
            "weight": record.weight if record else None,
            "mood": record.mood if record else None,
        })

    filled = [d for d in daily if d["sleep_hours"] or d["exercise_minutes"]]
    avg_sleep = round(sum(d["sleep_hours"] for d in filled) / len(filled), 2) if filled else 0
    avg_exercise = round(sum(d["exercise_minutes"] for d in filled) / len(filled), 1) if filled else 0
    week_exercise = sum(d["exercise_minutes"] for d in daily)
    weights = [d["weight"] for d in daily if d["weight"]]
    today_record = by_date.get(date.today().isoformat())

    tips = []
    if avg_sleep and avg_sleep < setting.target_sleep_minutes / 60 - 0.5:
        tips.append(f"平均睡眠 {avg_sleep}h 低于目标 {setting.target_sleep_minutes / 60:.1f}h，建议固定入睡时间")
    if week_exercise < setting.target_exercise_minutes:
        tips.append(f"本周运动 {week_exercise} 分钟，距周目标 {setting.target_exercise_minutes} 分钟还差 "
                    f"{setting.target_exercise_minutes - week_exercise} 分钟")
    if today_record and today_record.water_ml < setting.target_water_ml:
        tips.append(f"今日饮水 {today_record.water_ml}ml，建议补充至 {setting.target_water_ml}ml")
    if not tips:
        tips.append("各项指标达标，保持当前节奏 ✦")

    return {
        "range": {"days": days},
        "avg_sleep_hours": avg_sleep,
        "avg_exercise_minutes": avg_exercise,
        "week_exercise_minutes": week_exercise,
        "exercise_goal_rate": round(week_exercise / setting.target_exercise_minutes, 3)
        if setting.target_exercise_minutes else 0,
        "weight_change": round(weights[-1] - weights[0], 1) if len(weights) >= 2 else None,
        "sedentary": sedentary_status(db, user_id),
        "daily": daily,
        "tips": tips,
        "today": today_record.to_dict() if today_record else None,
    }
