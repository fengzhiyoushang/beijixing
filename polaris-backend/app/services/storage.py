"""文件存储：上传落盘（知识库文档 / 教室照片）。"""
from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from app.core.config import settings
from app.core.exceptions import AppError

DOC_EXT = {".md", ".markdown", ".txt", ".docx", ".xlsx"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}


def _target(kind: str) -> Path:
    folder = settings.upload_path / kind / datetime.now().strftime("%Y%m")
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_upload(kind: str, filename: str, data: bytes) -> dict:
    """保存上传文件，返回 {path, url, size, ext}。kind: docs | classroom | avatars"""
    ext = Path(filename or "").suffix.lower()
    allowed = DOC_EXT if kind == "docs" else IMAGE_EXT if kind == "classroom" else IMAGE_EXT | DOC_EXT
    if ext not in allowed:
        raise AppError(f"不支持的文件类型 {ext or '(无扩展名)'}，允许：{', '.join(sorted(allowed))}")

    max_bytes = settings.MAX_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise AppError(f"文件超过 {settings.MAX_UPLOAD_MB}MB 限制")
    if not data:
        raise AppError("文件内容为空")

    folder = _target(kind)
    name = f"{uuid.uuid4().hex}{ext}"
    path = folder / name
    path.write_bytes(data)

    rel = path.relative_to(settings.upload_path.parent).as_posix()
    return {"path": str(path), "rel_path": rel, "url": f"/{rel}",
            "size": len(data), "ext": ext, "filename": filename}
