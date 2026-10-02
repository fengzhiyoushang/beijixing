"""通用小工具：分页响应组装、排序白名单、文本处理。"""
from __future__ import annotations

import re
from typing import Iterable, Sequence


def page_response(items: Sequence, total: int, page: int, page_size: int) -> dict:
    return {
        "items": list(items),
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": (total + page_size - 1) // page_size if page_size else 0,
    }


def pick_sort(column_map: dict, sort_by: str | None, order: str = "desc"):
    """排序白名单，避免 SQL 注入。"""
    col = column_map.get(sort_by or "", None)
    if col is None:
        return None
    return col.desc() if order.lower() != "asc" else col.asc()


def strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "")


def clean_text(text: str | None) -> str:
    return re.sub(r"[ \t\u3000]+", " ", (text or "").replace("\r\n", "\n")).strip()


def truncate(text: str, limit: int = 200) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


def chunked(seq: Iterable, size: int) -> list[list]:
    buf: list = []
    out: list[list] = []
    for item in seq:
        buf.append(item)
        if len(buf) >= size:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out
