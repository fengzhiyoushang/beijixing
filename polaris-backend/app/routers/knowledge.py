"""知识库路由：文件夹、文档、上传解析、全文检索、向量化、RAG 问答、量化统计。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.ai import rag
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.exceptions import AppError
from app.models.user import User
from app.schemas.knowledge import DocIn, DocUpdate, FolderIn, FolderUpdate, QaIn, SearchIn
from app.services import knowledge_service, storage

router = APIRouter(prefix="/knowledge", tags=["⑧ 知识库"])


# ─────────── 文件夹 ───────────
@router.get("/folders", summary="文件夹列表")
def list_folders(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    folders = knowledge_service.list_folders(db, user.id)
    counts = {}
    for folder in folders:
        counts[folder.id] = len(knowledge_service.list_docs(db, user.id, folder_id=folder.id, limit=1000))
    return {"items": [{**f.to_dict(), "doc_count": counts.get(f.id, 0)} for f in folders]}


@router.post("/folders", summary="新建文件夹")
def create_folder(body: FolderIn, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    return knowledge_service.create_folder(db, user.id, body).to_dict()


@router.put("/folders/{folder_id}", summary="重命名/移动文件夹")
def update_folder(folder_id: int, body: FolderUpdate, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    return knowledge_service.update_folder(db, user.id, folder_id, body).to_dict()


@router.delete("/folders/{folder_id}", summary="删除文件夹（可选连带删除文档）")
def delete_folder(folder_id: int, delete_docs: bool = Query(default=False),
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return knowledge_service.delete_folder(db, user.id, folder_id, delete_docs=delete_docs)


# ─────────── 检索与问答 ───────────
@router.post("/search", summary="检索（关键词 / 向量 / 混合三种模式）")
def search(body: SearchIn, db: Session = Depends(get_db),
           user: User = Depends(get_current_user)) -> dict:
    if body.mode == "keyword":
        docs = rag.keyword_search_docs(db, user.id, body.keyword, limit=body.top_k)
        return {"mode": "keyword", "docs": docs, "chunks": []}
    chunks = rag.search(db, user.id, body.keyword, top_k=body.top_k, folder_id=body.folder_id,
                        mode=body.mode)
    docs = rag.keyword_search_docs(db, user.id, body.keyword, limit=body.top_k)
    return {"mode": body.mode, "chunks": chunks, "docs": docs}


@router.post("/qa", summary="RAG 问答（检索 → prompt → DeepSeek，附引用）")
async def qa(body: QaIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    return await rag.answer(db, user, body.question, top_k=body.top_k, doc_ids=body.doc_ids,
                            folder_id=body.folder_id, mode=body.mode, history=body.history)


@router.get("/stats", summary="知识库量化统计（文档数/字数/覆盖率/入库节奏/高频标签）")
def stats(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    return knowledge_service.stats(db, user.id)


# ─────────── 文档 ───────────
@router.get("/docs", summary="文档列表")
def list_docs(folder_id: int | None = Query(default=None), keyword: str | None = Query(default=None),
              tag: str | None = Query(default=None), vector_status: str | None = Query(default=None),
              limit: int = Query(default=100, ge=1, le=500),
              db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    docs = knowledge_service.list_docs(db, user.id, folder_id=folder_id, keyword=keyword, tag=tag,
                                       vector_status=vector_status, limit=limit)
    return {"total": len(docs), "items": [d.to_dict() for d in docs]}


@router.post("/docs", summary="新建文档（默认自动切片向量化）")
async def create_doc(body: DocIn, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    doc = knowledge_service.create_doc(db, user.id, body)
    if body.auto_vectorize and doc.content:
        info = await rag.build_index(db, doc)
        db.refresh(doc)
        return {**doc.to_dict(), "vectorize": info}
    return doc.to_dict()


@router.get("/docs/{doc_id}", summary="文档详情（含正文）")
def get_doc(doc_id: int, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> dict:
    doc = knowledge_service.get_doc(db, user.id, doc_id)
    return doc.to_dict(with_content=True)


@router.put("/docs/{doc_id}", summary="更新文档（re_vectorize=true 重建向量）")
async def update_doc(doc_id: int, body: DocUpdate, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> dict:
    doc = knowledge_service.update_doc(db, user.id, doc_id, body)
    if body.re_vectorize:
        await rag.build_index(db, doc)
        db.refresh(doc)
    return doc.to_dict(with_content=True)


@router.delete("/docs/{doc_id}", summary="删除文档（连带切片）")
def delete_doc(doc_id: int, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    knowledge_service.delete_doc(db, user.id, doc_id)
    return {"deleted": True}


@router.post("/docs/{doc_id}/vectorize", summary="手动（重新）向量化")
async def vectorize(doc_id: int, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    doc = knowledge_service.get_doc(db, user.id, doc_id)
    info = await rag.build_index(db, doc)
    return {"ok": True, **info}


@router.get("/docs/{doc_id}/chunks", summary="查看文档切片（调试检索效果）")
def chunks(doc_id: int, with_embedding: bool = Query(default=False),
           db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    doc = knowledge_service.get_doc(db, user.id, doc_id)
    return {"total": len(doc.chunks),
            "items": [c.to_dict(with_embedding=with_embedding) for c in doc.chunks]}


@router.post("/upload", summary="上传文档（md/txt/docx/xlsx）→ 解析 → 入库 → 向量化")
async def upload(file: UploadFile = File(...), folder_id: int | None = Query(default=None),
                 tags: str | None = Query(default=None, description="逗号分隔"),
                 auto_vectorize: bool = Query(default=True),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    data = await file.read()
    if not data:
        raise AppError("文件内容为空")
    saved = storage.save_upload("docs", file.filename or "doc.md", data)
    content = knowledge_service.extract_text(file.filename or "doc.md", data)
    if not content.strip():
        raise AppError("未能从文件中解析出文本内容")

    title = (file.filename or "未命名文档").rsplit(".", 1)[0]
    payload = DocIn(
        title=title, content=content, folder_id=folder_id,
        tags=[t.strip() for t in (tags or "").split(",") if t.strip()],
        doc_type=(file.filename or "").rsplit(".", 1)[-1].lower(), auto_vectorize=False,
    )
    doc = knowledge_service.create_doc(db, user.id, payload)
    doc.file_path = saved["rel_path"]
    db.commit()

    info = None
    if auto_vectorize:
        info = await rag.build_index(db, doc)
        db.refresh(doc)
    return {**doc.to_dict(), "vectorize": info}
