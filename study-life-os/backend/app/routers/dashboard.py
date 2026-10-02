"""首页总览聚合：双端共用，Redis/内存缓存 60s。"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models as m
from app.core.cache import cache
from app.core.database import get_db
from app.core.deps import get_current_user
from app.services import dashboard as dash_svc

router = APIRouter(prefix="/dashboard", tags=["总览仪表盘"])


@router.get("/summary")
def summary(db: Session = Depends(get_db), user: m.User = Depends(get_current_user)):
    key = f"sl:dashboard:{user.id}"
    return cache.get_or_set(key, 60, lambda: dash_svc.build_summary(db, user))
