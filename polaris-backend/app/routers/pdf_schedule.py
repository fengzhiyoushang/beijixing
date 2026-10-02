"""PDF 教室课表路由：多文件上传解析、结构化查询、删除。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.models.user import User
from app.services import pdf_schedule_service, storage

router = APIRouter(prefix="/pdf-schedule", tags=["⑭ PDF 教室课表"])


@router.post("/upload", summary="上传 PDF 教室课表（支持多文件）")
async def upload(
    files: list[UploadFile] = File(..., description="一个或多个 PDF 课表文件"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    if len(files) > 10:
        raise AppError("单次最多上传 10 个文件")
    results = []
    for f in files:
        data = await f.read()
        pdf_schedule_service.validate_upload(f.filename, f.content_type, data)
        saved = None
        try:
            saved = storage.save_upload("pdf_schedule", f.filename, data)
        except AppError:
            saved = None  # 落盘失败不影响解析结果展示
        upload_rec = await pdf_schedule_service.parse_and_store(
            db, user.id, f.filename or "未命名.pdf", data,
            stored_path=(saved or {}).get("path"))
        results.append(upload_rec.to_dict(with_entries=True))
    ok = sum(1 for r in results if r["status"] != "failed")
    return {"total": len(results), "succeeded": ok, "failed": len(results) - ok,
            "items": results}


@router.get("/uploads", summary="上传记录列表")
def uploads(limit: int = Query(default=50, ge=1, le=200),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    recs = pdf_schedule_service.list_uploads(db, user.id, limit=limit)
    return {"total": len(recs), "items": [r.to_dict() for r in recs]}


@router.get("/uploads/{upload_id}", summary="上传记录详情（含解析条目）")
def upload_detail(upload_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    return pdf_schedule_service.get_upload(db, user.id, upload_id).to_dict(with_entries=True)


@router.delete("/uploads/{upload_id}", summary="删除上传记录（连同解析条目）")
def delete_upload(upload_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    pdf_schedule_service.delete_upload(db, user.id, upload_id)
    return {"deleted": True}


@router.get("/entries", summary="解析条目查询（教室/日期/星期/周次/课程类型/关键词筛选）")
def entries(room_no: str | None = Query(default=None),
            weekday: int | None = Query(default=None, ge=1, le=7),
            week: int | None = Query(default=None, ge=1, le=30),
            day: date | None = Query(default=None, description="具体日期，自动换算星期与教学周"),
            keyword: str | None = Query(default=None),
            course_type: str | None = Query(default=None, description="理论/实验/体育/实践/公共基础"),
            upload_id: int | None = Query(default=None),
            limit: int = Query(default=500, ge=1, le=2000),
            db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return pdf_schedule_service.query_entries(
        db, user.id, room_no=room_no, weekday=weekday, week=week, date_=day,
        keyword=keyword, course_type=course_type, upload_id=upload_id, limit=limit)


@router.get("/options", summary="筛选器选项（教室/课程/教师/课程类型）")
def options(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return pdf_schedule_service.filter_options(db, user.id)
