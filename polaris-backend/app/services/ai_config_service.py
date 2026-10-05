"""大模型用户级配置 + Token 用量统计。

- 配置存于 users.config.llm（base_url / api_key / model / vl_model / timeout / quota），
  未配置时后端回退全局 .env（DeepSeek 默认值）。
- 用量台账 ai_usage 只记录真实调用（provider 返回的 usage 原样落库；
  provider 未回传时按字符数估算并标记 estimated=True），mock 演示模式不记账。
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.models.ai import AiUsage

CONFIG_KEY = "***"


def get_llm_cfg(user) -> dict:
    """用户自定义模型配置（可能为空 dict）。"""
    return dict((user.config or {}).get(CONFIG_KEY) or {})


def set_llm_cfg(db: Session, user, cfg: dict) -> dict:
    """保存模型配置（None 值字段视为删除该项，回退全局默认）。整体替换触发脏检查。"""
    merged = dict((user.config or {}).get(CONFIG_KEY) or {})
    for k, v in cfg.items():
        if v is None or v == "":
            merged.pop(k, None)
        else:
            merged[k] = v
    config = dict(user.config or {})
    config[CONFIG_KEY] = merged
    user.config = config
    db.commit()
    db.refresh(user)
    return merged


def mask_key(key: str | None) -> str:
    """API Key 脱敏展示：sk-abc…xyz"""
    k = (key or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return k[:2] + "…"
    return f"{k[:4]}…{k[-4:]}"


def public_cfg(user) -> dict:
    """返回给前端的配置（Key 脱敏）。"""
    cfg = get_llm_cfg(user)
    key = cfg.get("api_key") or ""
    return {
        "base_url": cfg.get("base_url", ""),
        "model": cfg.get("model", ""),
        "vl_model": cfg.get("vl_model", ""),
        "timeout": cfg.get("timeout", 60),
        "quota": cfg.get("quota", 0),
        "api_key_masked": mask_key(key),
        "has_key": bool(key.strip()),
    }


def usage_summary(db: Session, user_id: int, quota: int = 0) -> dict:
    """真实用量汇总：累计 / 今日 / 7 天 / 30 天 / 按模型。剩余 = 预算 - 累计（未设预算为 None）。"""
    base = select(
        func.coalesce(func.sum(AiUsage.total_tokens), 0),
        func.coalesce(func.sum(case((AiUsage.estimated == True, 1), else_=0)), 0),  # noqa: E712
        func.count(AiUsage.id),
    ).where(AiUsage.user_id == user_id)

    def _summed(since: datetime | None = None) -> tuple[int, int, int]:
        q = base
        if since:
            q = q.where(AiUsage.created_at >= since)
        row = db.execute(q).one()
        return int(row[0]), int(row[1]), int(row[2])

    now = datetime.now()
    total, est_total, calls = _summed()
    today, _, today_calls = _summed(now.replace(hour=0, minute=0, second=0, microsecond=0))
    week, _, _ = _summed(now - timedelta(days=7))
    month, _, _ = _summed(now - timedelta(days=30))
    by_model = db.execute(
        select(AiUsage.model, func.sum(AiUsage.total_tokens), func.count(AiUsage.id))
        .where(AiUsage.user_id == user_id)
        .group_by(AiUsage.model)
        .order_by(func.sum(AiUsage.total_tokens).desc())
    ).all()
    return {
        "total_tokens": total,
        "today_tokens": today,
        "week_tokens": week,
        "month_tokens": month,
        "calls": calls,
        "today_calls": today_calls,
        "estimated_rows": est_total,
        "quota": quota or 0,
        "remaining": (max(quota - total, 0) if quota else None),
        "by_model": [{"model": m or "unknown", "tokens": int(t or 0), "calls": int(c or 0)}
                     for m, t, c in by_model],
    }


def recent_usage(db: Session, user_id: int, limit: int = 20) -> list[dict]:
    rows = db.scalars(
        select(AiUsage).where(AiUsage.user_id == user_id)
        .order_by(AiUsage.id.desc()).limit(limit)
    ).all()
    return [r.to_dict() for r in rows]
