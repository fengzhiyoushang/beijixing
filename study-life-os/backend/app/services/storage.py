"""上传文件落盘：白名单校验、按类型/月份分目录、uuid 重命名。"""
import os
import re
import uuid
from datetime import datetime

from fastapi import HTTPException

from app.core.config import settings

ALLOWED = {
    "classroom": {".jpg", ".jpeg", ".png", ".webp"},
    "knowledge": {".md", ".txt", ".docx", ".xlsx"},
}
MAX_SIZE = {"classroom": 5 * 1024 * 1024, "knowledge": 10 * 1024 * 1024}


def save_upload(content: bytes, filename: str, kind: str) -> str:
    """返回前端可直接访问的相对 URL：/uploads/{kind}/{yyyymm}/{uuid}.ext"""
    if kind not in ALLOWED:
        raise HTTPException(400, f"未知上传类型 {kind}")
    if len(content) > MAX_SIZE[kind]:
        raise HTTPException(413, "文件超过大小限制")
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED[kind]:
        raise HTTPException(400, f"不支持的文件格式 {ext}")
    yyyymm = datetime.now().strftime("%Y%m")
    rel_dir = os.path.join(settings.UPLOAD_DIR, kind, yyyymm)
    os.makedirs(os.path.join(os.getcwd(), rel_dir), exist_ok=True)
    safe_ext = re.sub(r"[^.\w]", "", ext)
    name = f"{uuid.uuid4().hex}{safe_ext}"
    abs_path = os.path.join(os.getcwd(), rel_dir, name)
    with open(abs_path, "wb") as f:
        f.write(content)
    return f"/uploads/{kind}/{yyyymm}/{name}"
