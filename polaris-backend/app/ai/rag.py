"""RAG：文本切片 → 向量化入库 → 混合检索 → 组装 prompt → 生成答案。"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.ai import prompts
from app.ai.deepseek import deepseek
from app.ai.embeddings import cosine, keyword_score, local_embeddings
from app.core.config import settings
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc
from app.utils.pagination import clean_text

logger = logging.getLogger("polaris.rag")


# ────────────── 切片 ──────────────
def chunk_text(text: str, size: int | None = None, overlap: int | None = None) -> list[str]:
    """按段落聚合切片，超长段落按窗口滑分，保证语义边界尽量完整。"""
    size = size or settings.RAG_CHUNK_SIZE
    overlap = overlap if overlap is not None else settings.RAG_CHUNK_OVERLAP
    text = clean_text(text)
    if not text:
        return []
    paragraphs, buf = [], ""
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(para) > size:                     # 长段落按窗口切
            if buf:
                paragraphs.append(buf)
                buf = ""
            step = max(1, size - overlap)
            for i in range(0, len(para), step):
                paragraphs.append(para[i:i + size])
        elif len(buf) + len(para) + 1 <= size:
            buf = f"{buf}\n{para}" if buf else para
        else:
            paragraphs.append(buf)
            buf = para
    if buf:
        paragraphs.append(buf)
    return [p for p in paragraphs if p.strip()]


# ────────────── 索引 ──────────────
async def build_index(db: Session, doc: KnowledgeDoc) -> dict:
    """重建某文档的向量索引（删除旧切片 → 切片 → 向量化 → 落库）。"""
    doc.vector_status = "processing"
    doc.vector_error = None
    db.commit()

    try:
        chunks = chunk_text(doc.content or "")
        if not chunks:
            doc.vector_status = "done"
            doc.vector_count = 0
            db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
            db.commit()
            return {"doc_id": doc.id, "chunks": 0, "provider": "none"}

        provider = "local"
        vectors = None
        if settings.EMBEDDING_PROVIDER == "deepseek":
            vectors = await deepseek.embeddings(chunks)
            if vectors:
                provider = "deepseek"
        if vectors is None:
            vectors = local_embeddings(chunks)

        db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete()
        for i, (content, vec) in enumerate(zip(chunks, vectors)):
            db.add(KnowledgeChunk(
                doc_id=doc.id, chunk_index=i, content=content,
                embedding=vec, dim=len(vec), tokens=len(content) // 2,
            ))
        doc.vector_status = "done"
        doc.vector_count = len(chunks)
        doc.embedded_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.commit()
        return {"doc_id": doc.id, "chunks": len(chunks), "provider": provider, "dim": len(vectors[0])}
    except Exception as exc:                     # pragma: no cover
        logger.exception("向量化失败 doc=%s", doc.id)
        doc.vector_status = "failed"
        doc.vector_error = str(exc)[:200]
        db.commit()
        raise


# ────────────── 检索 ──────────────
def _base_query(db: Session, user_id: int, doc_ids: list[int] | None, folder_id: int | None):
    query = (
        db.query(KnowledgeChunk, KnowledgeDoc)
        .join(KnowledgeDoc, KnowledgeChunk.doc_id == KnowledgeDoc.id)
        .filter(KnowledgeDoc.user_id == user_id)
    )
    if doc_ids:
        query = query.filter(KnowledgeDoc.id.in_(doc_ids))
    if folder_id:
        query = query.filter(KnowledgeDoc.folder_id == folder_id)
    return query


def search(
    db: Session,
    user_id: int,
    query_text: str,
    *,
    top_k: int | None = None,
    doc_ids: list[int] | None = None,
    folder_id: int | None = None,
    mode: str = "hybrid",
) -> list[dict]:
    """检索切片：keyword / vector / hybrid 三种模式。"""
    top_k = top_k or settings.RAG_TOP_K
    rows = _base_query(db, user_id, doc_ids, folder_id).all()
    if not rows:
        return []

    query_vec = local_embeddings([query_text])[0]
    hits: list[dict] = []
    for chunk, doc in rows:
        vec_score = cosine(query_vec, chunk.embedding or []) if chunk.embedding else 0.0
        kw_score = keyword_score(query_text, chunk.content)
        if mode == "keyword":
            score = kw_score
        elif mode == "vector":
            score = vec_score
        else:
            score = 0.65 * vec_score + 0.35 * kw_score
        if score <= 0:
            continue
        hits.append({
            "doc_id": doc.id,
            "doc_title": doc.title,
            "folder_id": doc.folder_id,
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "content": chunk.content,
            "vector_score": round(vec_score, 4),
            "keyword_score": round(kw_score, 4),
            "score": round(score, 4),
        })

    hits.sort(key=lambda x: -x["score"])
    # 简单去重：同一文档最多保留 3 段
    per_doc: dict[int, int] = {}
    deduped = []
    for hit in hits:
        count = per_doc.get(hit["doc_id"], 0)
        if count >= 3:
            continue
        per_doc[hit["doc_id"]] = count + 1
        deduped.append(hit)
        if len(deduped) >= top_k:
            break
    return deduped


def keyword_search_docs(db: Session, user_id: int, keyword: str, limit: int = 20) -> list[dict]:
    """文档级全文检索（标题 + 内容 LIKE），返回命中片段。"""
    like = f"%{keyword}%"
    docs = (
        db.query(KnowledgeDoc)
        .filter(
            KnowledgeDoc.user_id == user_id,
            or_(KnowledgeDoc.title.like(like), KnowledgeDoc.content.like(like),
                KnowledgeDoc.summary.like(like)),
        )
        .order_by(KnowledgeDoc.updated_at.desc())
        .limit(limit)
        .all()
    )
    out = []
    for doc in docs:
        content = doc.content or ""
        idx = content.find(keyword)
        snippet = content[max(0, idx - 60): idx + 140] if idx >= 0 else content[:160]
        # 命中次数（用于排序参考）
        out.append({**doc.to_dict(), "snippet": snippet, "hits": content.count(keyword)})
    out.sort(key=lambda x: -x["hits"])
    return out


def build_context(hits: list[dict], limit: int = 4000) -> str:
    parts, used = [], 0
    for i, hit in enumerate(hits, start=1):
        block = f"[资料{i}] 《{hit['doc_title']}》\n{hit['content']}"
        if used + len(block) > limit:
            break
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)


def extractive_answer(hits: list[dict]) -> str:
    """无 AI 时的抽取式答案：返回最相关片段 + 引用标注。"""
    if not hits:
        return "知识库中未找到相关内容。建议先在「知识整理」中上传或新建文档后再提问。"
    lines = ["（AI 未配置或调用失败，以下为检索到的原始片段）"]
    for i, hit in enumerate(hits[:3], start=1):
        snippet = hit["content"][:220].replace("\n", " ")
        lines.append(f"{i}. {snippet}… [资料{i}] 《{hit['doc_title']}》")
    return "\n".join(lines)


def _record(db: Session, user, res: dict) -> None:
    """把 RAG 调用的真实 usage 记入用量台账（局部导入避免循环依赖）。"""
    from app.services import ai_service

    ai_service.record_usage(db, user.id, None, res.get("model"), res.get("usage"))


async def answer(
    db: Session,
    user,
    question: str,
    *,
    top_k: int | None = None,
    doc_ids: list[int] | None = None,
    folder_id: int | None = None,
    mode: str = "auto",
    history: list[dict] | None = None,
) -> dict:
    """RAG 问答主流程，返回 {answer, references, mode, hits}。"""
    hits = search(db, user.id, question, top_k=top_k, doc_ids=doc_ids, folder_id=folder_id)

    if mode == "chat" or (mode == "auto" and not hits):
        messages = [{"role": "system", "content": prompts.SYSTEM_ASSISTANT.format(
            now=datetime.now().strftime("%Y-%m-%d %H:%M"), nickname=user.nickname or user.username,
            school=(user.config or {}).get("school", "华中科技大学"),
            role=(user.config or {}).get("role", "考研备战中"))}]
        messages += (history or [])[-6:]
        messages.append({"role": "user", "content": question})
        res = await deepseek.chat(messages, temperature=0.6)
        _record(db, user, res)
        return {
            "answer": (res.get("message") or {}).get("content") or "",
            "references": [],
            "mode": "chat" if deepseek.is_configured else "chat-mock",
            "hits": [],
        }

    if not hits:
        return {"answer": extractive_answer([]), "references": [], "mode": "empty", "hits": []}

    if settings.EMBEDDING_PROVIDER == "local" and not deepseek.is_configured:
        return {
            "answer": extractive_answer(hits),
            "references": _refs(hits),
            "mode": "extractive",
            "hits": hits,
        }

    context = build_context(hits)
    messages = [
        {"role": "system", "content": "你是严谨的知识库问答助手，只依据给定资料回答。"},
        {"role": "user", "content": prompts.RAG_PROMPT.format(context=context, question=question)},
    ]
    try:
        res = await deepseek.chat(messages, temperature=0.3)
        _record(db, user, res)
        answer_text = (res.get("message") or {}).get("content") or extractive_answer(hits)
        mode_used = "rag" if deepseek.is_configured else "rag-mock"
    except Exception as exc:                     # pragma: no cover
        logger.warning("RAG 生成失败，回退抽取式：%s", exc)
        answer_text, mode_used = extractive_answer(hits), "extractive"

    # 引用计数
    for doc_id in {h["doc_id"] for h in hits}:
        doc = db.get(KnowledgeDoc, doc_id)
        if doc:
            doc.read_count = (doc.read_count or 0) + 1
    db.commit()

    return {"answer": answer_text, "references": _refs(hits), "mode": mode_used, "hits": hits}


def _refs(hits: list[dict]) -> list[dict]:
    seen, refs = set(), []
    for i, hit in enumerate(hits, start=1):
        if hit["doc_id"] in seen:
            continue
        seen.add(hit["doc_id"])
        refs.append({
            "index": len(refs) + 1,
            "doc_id": hit["doc_id"],
            "doc_title": hit["doc_title"],
            "score": hit["score"],
            "snippet": hit["content"][:160],
        })
    return refs
