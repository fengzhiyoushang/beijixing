"""微信订阅消息推送服务。

关键约束（务必了解）：
- 个人主体小程序只能使用**一次性订阅消息**：用户授权几次，就只能推送几条；
- 因此这里做三件事：① 精确记账配额；② 推送去重（同一任务只提醒一次）；③ 失败降级不阻塞业务。

未配置 WX_APPID / WX_APP_SECRET 时进入演示模式：只写日志不实际发送，便于本地联调。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from app.core.cache import cache
from app.core.config import settings
from app.models.task import DdlTask
from app.models.user import User
from app.models.wechat import WxPushLog, WxSubscriptionQuota
from app.services import course_service

logger = logging.getLogger("polaris.wechat")

KIND_DDL = "ddl"
KIND_CLASS = "class"
KINDS = (KIND_DDL, KIND_CLASS)

_TOKEN_KEY = "polaris:wx:access_token"
_API = "https://api.weixin.qq.com"

# 模板字段映射：微信要求 data 的 key 与模板中的字段编号一致（thing1/time2…）
DEFAULT_MAP = {
    KIND_DDL: {"title": "thing1", "due_at": "time2", "category": "thing3"},
    KIND_CLASS: {"name": "thing1", "start_time": "time2", "location": "thing3"},
}


def status() -> dict:
    return {
        "configured": settings.wechat_configured,
        "push_enabled": settings.WX_PUSH_ENABLED,
        "mode": "live" if settings.wechat_configured else "mock",
        "appid": settings.WX_APPID or None,
        "appsecret_configured": bool(settings.WX_APP_SECRET.strip()),
        "templates": {"ddl": settings.WX_TEMPLATE_DDL or None,
                      "class": settings.WX_TEMPLATE_CLASS or None},
        "ahead_minutes": {"ddl": settings.WX_DDL_AHEAD_MINUTES,
                          "class": settings.WX_CLASS_AHEAD_MINUTES},
        "scheduler_enabled": settings.WX_SCHEDULER_ENABLED,
        "hint": _hint(),
    }


def _hint() -> str | None:
    """区分「完全没配」「只差 AppSecret」「只差模板 ID」三种状态，便于排查。"""
    if settings.wechat_configured:
        if not (settings.WX_TEMPLATE_DDL or settings.WX_TEMPLATE_CLASS):
            return "已配置 AppID/AppSecret，还差订阅消息模板 ID（公众平台 → 订阅消息 → 我的模板）"
        return None
    if settings.WX_APPID.strip():
        return ("已配置 AppID（%s），还差 AppSecret（公众平台 → 开发管理 → 开发设置）"
                "与模板 ID；当前推送只写日志不实际发送" % settings.WX_APPID)
    return "未配置 WX_APPID / WX_APP_SECRET：推送只写日志不实际发送（可在「我的」页验证订阅链路）"


# ─────────── access_token ───────────
async def get_access_token(force: bool = False) -> str | None:
    """获取并缓存 access_token（微信有效期 7200s，缓存 7000s）。"""
    if not settings.wechat_configured:
        return None
    if not force:
        cached = cache.get(_TOKEN_KEY)
        if cached:
            return cached
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{_API}/cgi-bin/token", params={
                "grant_type": "client_credential",
                "appid": settings.WX_APPID,
                "secret": settings.WX_APP_SECRET,
            })
        data = resp.json()
        token = data.get("access_token")
        if not token:
            logger.warning("获取 access_token 失败：%s", data)
            return None
        cache.set(_TOKEN_KEY, token, ttl=int(data.get("expires_in", 7200)) - 200)
        return token
    except Exception as exc:                     # pragma: no cover - 网络相关
        logger.warning("获取 access_token 异常：%s", exc)
        return None


# ─────────── 配额记账 ───────────
def _template_of(kind: str) -> str:
    return settings.template_of(kind) or f"unset:{kind}"


def get_quota(db: Session, user_id: int, kind: str) -> WxSubscriptionQuota | None:
    template_id = _template_of(kind)
    return (db.query(WxSubscriptionQuota)
            .filter(WxSubscriptionQuota.user_id == user_id,
                    WxSubscriptionQuota.template_id == template_id).first())


def grant_quota(db: Session, user_id: int, kind: str, times: int = 1,
                template_id: str | None = None) -> WxSubscriptionQuota:
    """记录一次（或多次）用户授权，累加可推送次数。"""
    kind = kind if kind in KINDS else KIND_DDL
    template_id = template_id or _template_of(kind)
    quota = (db.query(WxSubscriptionQuota)
             .filter(WxSubscriptionQuota.user_id == user_id,
                     WxSubscriptionQuota.template_id == template_id).first())
    if not quota:
        quota = WxSubscriptionQuota(user_id=user_id, template_id=template_id, kind=kind)
        db.add(quota)
    times = max(1, min(int(times or 1), 50))
    quota.kind = kind
    quota.granted_total = (quota.granted_total or 0) + times
    quota.remaining = (quota.remaining or 0) + times
    quota.last_granted_at = datetime.now()
    db.commit()
    db.refresh(quota)
    logger.info("用户 %s 授权 %s 消息 %s 次，剩余 %s 次", user_id, kind, times, quota.remaining)
    return quota


def _consume(db: Session, quota: WxSubscriptionQuota, count: int = 1) -> None:
    quota.used_total = (quota.used_total or 0) + count
    quota.remaining = max(0, (quota.remaining or 0) - count)
    quota.last_used_at = datetime.now()
    db.commit()


def quota_overview(db: Session, user_id: int) -> list[dict]:
    rows = (db.query(WxSubscriptionQuota)
            .filter(WxSubscriptionQuota.user_id == user_id).all())
    by_kind = {r.kind: r.to_dict() for r in rows}
    out = []
    for kind in KINDS:
        item = by_kind.get(kind) or {"kind": kind, "template_id": _template_of(kind),
                                     "granted_total": 0, "used_total": 0, "remaining": 0,
                                     "last_granted_at": None, "last_used_at": None}
        # 未配置模板时给出提示字段
        item["template_configured"] = bool(settings.template_of(kind))
        out.append(item)
    return out


# ─────────── 数据组装与发送 ───────────
def _clip(text: str | None, limit: int = 20) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt_time(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "未设置"


def build_data(kind: str, context: dict) -> dict:
    """按模板字段映射组装 data（微信限制：thing ≤ 20 字符）。"""
    mapping = DEFAULT_MAP.get(kind, DEFAULT_MAP[KIND_DDL])
    values = {
        "title": _clip(context.get("title")),
        "due_at": _fmt_time(context.get("due_at")),
        "category": _clip(context.get("category") or "学习"),
        "name": _clip(context.get("name")),
        "start_time": _fmt_time(context.get("start_time")),
        "location": _clip(context.get("location")),
    }
    data = {}
    for field, wx_key in mapping.items():
        data[wx_key] = {"value": values.get(field) or "—"}
    return data


async def send(db: Session, user: User, kind: str, context: dict, *,
               page: str | None = None, dedup_key: str | None = None) -> dict:
    """发送一条订阅消息（含配额检查、去重、日志）。"""
    kind = kind if kind in KINDS else KIND_DDL
    template_id = settings.template_of(kind)
    openid = user.wx_openid
    page = page or ("pages/ddl/list" if kind == KIND_DDL else "pages/index/index")

    def log(status: str, *, errcode: int | None = None, errmsg: str | None = None) -> dict:
        entry = WxPushLog(user_id=user.id, kind=kind, template_id=template_id, openid=openid,
                          page=page, payload=build_data(kind, context), dedup_key=dedup_key,
                          status=status, errcode=errcode, errmsg=errmsg)
        db.add(entry)
        db.commit()
        db.refresh(entry)
        return entry.to_dict()

    if not settings.WX_PUSH_ENABLED:
        return log("skipped_not_configured", errmsg="WX_PUSH_ENABLED=false")
    if not openid:
        return log("skipped_no_openid", errmsg="用户未绑定微信 openid")

    if dedup_key:
        exists = (db.query(WxPushLog)
                  .filter(WxPushLog.user_id == user.id, WxPushLog.dedup_key == dedup_key,
                          WxPushLog.status == "success").first())
        if exists:
            return log("skipped_duplicate", errmsg=f"已推送过 {dedup_key}")

    quota = get_quota(db, user.id, kind)
    if not quota or (quota.remaining or 0) <= 0:
        return log("skipped_no_quota", errmsg="一次性订阅额度已用完，请在小程序中重新授权")

    if not settings.wechat_configured:
        # 演示模式：完整走一遍配额记账与日志，但不实际调用微信接口（便于本地联调）
        _consume(db, quota)
        return log("success", errmsg="演示模式：未配置 WX_APPID/WX_APP_SECRET，未实际发送")

    if not template_id:
        return log("skipped_not_configured", errmsg=f"未配置 {kind} 模板 ID")

    token = await get_access_token()
    if not token:
        return log("failed", errmsg="access_token 获取失败")

    body = {
        "touser": openid,
        "template_id": template_id,
        "page": page,
        "miniprogram_state": settings.WX_MP_STATE,
        "lang": "zh_CN",
        "data": build_data(kind, context),
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(f"{_API}/cgi-bin/message/subscribe/send",
                                     params={"access_token": token}, json=body)
        result = resp.json()
    except Exception as exc:                     # pragma: no cover
        return log("failed", errmsg=f"请求异常：{exc}")

    errcode = result.get("errcode", 0)
    if errcode == 0:
        _consume(db, quota)
        return log("success")
    if errcode in (40001, 42001):                # token 失效：刷新后重试一次
        token = await get_access_token(force=True)
        if token:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(f"{_API}/cgi-bin/message/subscribe/send",
                                         params={"access_token": token}, json=body)
            result = resp.json()
            errcode = result.get("errcode", 0)
            if errcode == 0:
                _consume(db, quota)
                return log("success")
    if errcode == 43101:                         # 用户已拒绝/授权已消耗
        quota.remaining = 0
        db.commit()
    return log("failed", errcode=errcode, errmsg=result.get("errmsg"))


# ─────────── 扫描与推送 ───────────
async def push_due_ddl(db: Session, *, ahead_minutes: int | None = None,
                       limit: int = 200) -> dict:
    """扫描「即将到期」的任务并推送提醒（同一任务只推一次）。"""
    ahead = ahead_minutes or settings.WX_DDL_AHEAD_MINUTES
    now = datetime.now()
    deadline = now + timedelta(minutes=ahead)
    tasks = (db.query(DdlTask)
             .filter(DdlTask.status == "pending", DdlTask.due_at.isnot(None),
                     DdlTask.due_at >= now, DdlTask.due_at <= deadline)
             .order_by(DdlTask.due_at).limit(limit).all())

    sent = failed = skipped = 0
    details = []
    for task in tasks:
        user = db.get(User, task.user_id)
        if not user:
            continue
        dedup = f"ddl:{task.id}:{task.due_at.strftime('%Y%m%d%H%M')}"
        result = await send(db, user, KIND_DDL,
                            {"title": task.title, "due_at": task.due_at,
                             "category": task.category},
                            page="pages/ddl/list", dedup_key=dedup)
        status_value = result["status"]
        if status_value == "success":
            sent += 1
        elif status_value.startswith("skipped"):
            skipped += 1
        else:
            failed += 1
        details.append({"task_id": task.id, "title": task.title, "status": status_value,
                        "errmsg": result.get("errmsg")})
    return {"kind": KIND_DDL, "ahead_minutes": ahead, "candidates": len(tasks),
            "sent": sent, "skipped": skipped, "failed": failed, "details": details[:20]}


async def push_upcoming_class(db: Session, *, ahead_minutes: int | None = None) -> dict:
    """扫描今天即将开始的课程并推送提醒。"""
    ahead = ahead_minutes or settings.WX_CLASS_AHEAD_MINUTES
    now = datetime.now()
    deadline = now + timedelta(minutes=ahead)

    users = db.query(User).filter(User.wx_openid.isnot(None)).all()
    sent = failed = skipped = 0
    details = []
    for user in users:
        try:
            classes = course_service.today_classes(db, user.id)
        except Exception:                        # pragma: no cover
            continue
        for item in classes:
            start_time = item.get("start_time") or ""
            if ":" not in start_time:
                continue
            hour, minute = (int(x) for x in start_time.split(":")[:2])
            start_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if not (now <= start_dt <= deadline):
                continue
            dedup = f"class:{item['course_id']}:{now.strftime('%Y%m%d')}:{start_time}"
            result = await send(db, user, KIND_CLASS,
                                {"name": item.get("name"), "start_time": start_dt,
                                 "location": item.get("location")},
                                page="pages/timetable/timetable", dedup_key=dedup)
            status_value = result["status"]
            if status_value == "success":
                sent += 1
            elif status_value.startswith("skipped"):
                skipped += 1
            else:
                failed += 1
            details.append({"user_id": user.id, "course": item.get("name"),
                            "start_time": start_time, "status": status_value})
    return {"kind": KIND_CLASS, "ahead_minutes": ahead, "sent": sent,
            "skipped": skipped, "failed": failed, "details": details[:20]}


async def run_scan(db: Session) -> dict:
    """一次完整扫描（cron / 云托管定时触发器调用此逻辑）。"""
    ddl = await push_due_ddl(db)
    classes = await push_upcoming_class(db)
    logger.info("提醒扫描完成：DDL 发送 %s 条，上课提醒 %s 条", ddl["sent"], classes["sent"])
    return {"at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"), "ddl": ddl, "class": classes}


def recent_logs(db: Session, user_id: int, limit: int = 30) -> list[dict]:
    rows = (db.query(WxPushLog)
            .filter(WxPushLog.user_id == user_id)
            .order_by(WxPushLog.created_at.desc()).limit(limit).all())
    return [r.to_dict() for r in rows]
