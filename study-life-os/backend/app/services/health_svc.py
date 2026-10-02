"""久坐/作息状态服务：Web 与小程序共用的提醒判定逻辑。"""
from datetime import datetime, time

from sqlalchemy.orm import Session

from app.models.health import HealthSetting
from app.utils.timeutil import in_time_range


def get_or_create_settings(db: Session, user_id: int) -> HealthSetting:
    st = db.query(HealthSetting).filter(HealthSetting.user_id == user_id).first()
    if st is None:
        st = HealthSetting(user_id=user_id, last_heartbeat_at=datetime.now())
        db.add(st)
        db.commit()
        db.refresh(st)
    return st


def sedentary_status(db: Session, user_id: int) -> dict:
    """距上次活动的分钟数、是否应提醒起身。免打扰与睡眠时段静默。"""
    st = get_or_create_settings(db, user_id)
    now = datetime.now()
    base = st.last_heartbeat_at or now
    since_min = int((now - base).total_seconds() // 60)
    quiet = in_time_range(now.time(), st.quiet_start, st.quiet_end)
    active = in_time_range(now.time(), st.active_start, st.active_end)
    should = bool(
        st.sedentary_enabled
        and not quiet
        and active
        and since_min >= st.sedentary_interval_min
    )
    return {
        "sedentary_enabled": bool(st.sedentary_enabled),
        "interval_min": st.sedentary_interval_min,
        "minutes_since_break": since_min,
        "should_break": should,
        "in_quiet_hours": quiet,
        "message": f"已连续静坐 {since_min} 分钟，起身活动一下吧 💪" if should else None,
    }
