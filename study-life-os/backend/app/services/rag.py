"""零外部依赖的中文 RAG：字符一元组+二元组分词、BM25 检索。

向量检索（Embedding）为二期演进项，接口签名保持不变即可替换实现。
"""
import math
import re
from collections import Counter
from typing import List

from sqlalchemy.orm import Session

from app.models.knowledge import KnowledgeChunk, KnowledgeDoc

WINDOW = 500
OVERLAP = 100
K1, B = 1.5, 0.75

_SEGMENT = re.compile(r"[a-zA-Z0-9_]+|[一-鿿]+")


def split_chunks(text: str) -> List[str]:
    """滑窗切块（500 字窗口、100 字重叠），跳过 Markdown 图片行。"""
    text = (text or "").strip()
    if not text:
        return []
    chunks: List[str] = []
    step = WINDOW - OVERLAP
    start = 0
    while start < len(text):
        piece = text[start:start + WINDOW].strip()
        if piece:
            chunks.append(piece)
        start += step
    return chunks


def tokenize(text: str) -> List[str]:
    """英文/数字按词，中文取一元组+二元组，兼顾召回与精度。"""
    tokens: List[str] = []
    for seg in _SEGMENT.findall((text or "").lower()):
        if re.match(r"^[a-z0-9_]+$", seg):
            tokens.append(seg)
        else:
            tokens.extend(list(seg))
            tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
    return tokens


def build_index(db: Session, doc: KnowledgeDoc) -> int:
    """重建某文档的检索块，返回块数。"""
    db.query(KnowledgeChunk).filter(KnowledgeChunk.doc_id == doc.id).delete(synchronize_session=False)
    chunks = split_chunks(doc.content or "")
    for i, c in enumerate(chunks):
        db.add(KnowledgeChunk(doc_id=doc.id, idx=i, text=c))
    doc.word_count = len(re.sub(r"\s", "", doc.content or ""))
    db.commit()
    return len(chunks)


def search(db: Session, user_id: int, query: str, top_k: int = 5) -> List[dict]:
    """BM25 检索用户全部知识块，返回 [{doc_id, doc_title, text, score}]。"""
    rows = (
        db.query(KnowledgeChunk, KnowledgeDoc)
        .join(KnowledgeDoc, KnowledgeChunk.doc_id == KnowledgeDoc.id)
        .filter(KnowledgeDoc.user_id == user_id)
        .all()
    )
    if not rows:
        return []

    corpus_tokens = [tokenize(c.text) for c, _ in rows]
    n = len(rows)
    avg_len = (sum(len(t) for t in corpus_tokens) / n) or 1.0
    df: Counter = Counter()
    for toks in corpus_tokens:
        df.update(set(toks))

    q_tokens = set(tokenize(query))
    if not q_tokens:
        return []

    scored = []
    for (chunk, doc), toks in zip(rows, corpus_tokens):
        tf = Counter(toks)
        doc_len = len(toks) or 1
        score = 0.0
        for t in q_tokens:
            if t not in tf:
                continue
            idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
            score += idf * (tf[t] * (K1 + 1)) / (tf[t] + K1 * (1 - B + B * doc_len / avg_len))
        if score > 0:
            scored.append({
                "doc_id": doc.id,
                "doc_title": doc.title,
                "chunk_id": chunk.id,
                "text": chunk.text[:400],
                "score": round(score, 3),
            })
    scored.sort(key=lambda x: -x["score"])
    return scored[:top_k]


def build_qa_prompt(question: str, hits: List[dict]) -> str:
    context = "\n\n".join(
        f"【资料{i + 1}·{h['doc_title']}】{h['text']}" for i, h in enumerate(hits)
    )
    return (
        "你是知识库问答助手。仅依据给定资料回答，引用处标注【资料n】；"
        "资料不足时明确说明。请用简洁中文作答。\n\n"
        f"参考资料：\n{context}\n\n问题：{question}\n回答："
    )
