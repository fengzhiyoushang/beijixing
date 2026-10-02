"""系统管理路由：配置管理、运行状态、库表统计、数据备份与恢复。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models.user import User
from app.schemas.system import BackupIn, ConfigIn, ConfigUpdate
from app.services import system_service

router = APIRouter(prefix="/system", tags=["⑪ 系统管理"])


@router.get("/runtime", summary="运行状态（数据库/缓存/AI/向量/限额）")
def runtime(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return system_service.runtime_info()


@router.get("/tables", summary="各表行数统计")
def tables(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return {"items": system_service.table_stats(db)}


# ─────────── 配置管理 ───────────
@router.get("/configs", summary="配置列表")
def list_configs(public_only: bool = Query(default=False), group: str | None = Query(default=None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    is_admin = user.role == "admin"
    configs = system_service.list_configs(db, public_only=public_only or not is_admin, group=group)
    return {"total": len(configs), "items": [c.to_dict() for c in configs]}


@router.post("/configs", summary="新增/覆盖配置项（键值 JSON）")
def set_config(body: ConfigIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    return system_service.set_config(db, body).to_dict()


@router.put("/configs/{key}", summary="更新配置项")
def update_config(key: str, body: ConfigUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    return system_service.update_config(db, key, body).to_dict()


@router.delete("/configs/{key}", summary="删除配置项")
def delete_config(key: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    system_service.delete_config(db, key)
    return {"deleted": True}


# ─────────── 数据备份 ───────────
@router.post("/backups", summary="创建数据备份（user=仅本人数据 / full=全库）")
def create_backup(body: BackupIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    record = system_service.create_backup(db, user.id, body)
    return record.to_dict()


@router.get("/backups", summary="备份列表")
def list_backups(include_full: bool = Query(default=False), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    records = system_service.list_backups(db, user.id, include_full=include_full)
    return {"total": len(records), "items": [r.to_dict() for r in records]}


@router.get("/backups/{backup_id}", summary="备份详情")
def get_backup(backup_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    return system_service.get_backup(db, user.id, backup_id).to_dict()


@router.delete("/backups/{backup_id}", summary="删除备份（含文件）")
def delete_backup(backup_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    system_service.delete_backup(db, user.id, backup_id)
    return {"deleted": True}


@router.post("/backups/{backup_id}/restore", summary="从备份恢复（危险操作，需 confirm=true）")
def restore_backup(backup_id: int, confirm: bool = Query(default=False),
                   db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return system_service.restore_backup(db, user.id, backup_id, confirm=confirm)
