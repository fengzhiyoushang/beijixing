"""文本向量化：远端 provider 优先，缺失时使用零依赖本地哈希向量。

本地向量：字符 unigram + bigram 哈希到固定维度，按词频加权后 L2 归一化。
优点：无外部依赖、确定性、中文友好；缺点：语义泛化弱于真实 embedding。
生产建议：设置 EMBEDDING_PROVIDER=deepseek（或替换为任意兼容 /embeddings 的服务）。
"""
from __future__ import annotations

import hashlib
import math
import re

from app.core.config import settings

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-zA-Z0-9]+")


def _tokens(text: str) -> list[str]:
    """中文单字 + 英文单词 + 中文双字组。"""
    base = _TOKEN_RE.findall((text or "").lower())
    grams = list(base)
    grams += ["".join(base[i:i + 2]) for i in range(len(base) - 1)]
    return grams


def _bucket(token: str, dim: int) -> int:
    digest = hashlib.md5(token.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big") % dim


def local_embedding(text: str, dim: int | None = None) -> list[float]:
    dim = dim or settings.EMBEDDING_DIM
    vec = [0.0] * dim
    tokens = _tokens(text)
    if not tokens:
        return vec
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    for token, count in counts.items():
        # 次线性词频 + 位置无关哈希
        weight = 1.0 + math.log(count)
        idx = _bucket(token, dim)
        sign = 1.0 if hashlib.md5(token.encode()).digest()[4] % 2 == 0 else -1.0
        vec[idx] += sign * weight
    norm = math.sqrt(sum(v * v for v in vec))
    return [v / norm for v in vec] if norm else vec


def local_embeddings(texts: list[str], dim: int | None = None) -> list[list[float]]:
    return [local_embedding(t, dim) for t in texts]


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    size = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(size))
    na = math.sqrt(sum(x * x for x in a[:size]))
    nb = math.sqrt(sum(x * x for x in b[:size]))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def keyword_score(query: str, text: str) -> float:
    """轻量关键词命中率（用于 hybrid 混合检索），归一化到 0~1。"""
    q = set(_tokens(query))
    if not q:
        return 0.0
    t = set(_tokens(text))
    hit = len(q & t)
    return min(1.0, hit / max(1, len(q) * 0.55))
