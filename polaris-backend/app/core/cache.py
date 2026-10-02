"""缓存层：Redis 优先，不可用时自动回退进程内 TTL 缓存。

对外统一接口：get / set / delete / get_or_set / incr / delete_prefix / health
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Callable

from app.core.config import settings

logger = logging.getLogger("polaris.cache")


class _MemoryCache:
    """线程安全的进程内 TTL 缓存（Redis 不可用时的降级实现）。"""

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> str | None:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            expire_at, value = item
            if expire_at and expire_at < time.time():
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (time.time() + ttl if ttl else 0, value)

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        with self._lock:
            keys = [k for k in self._data if k.startswith(prefix)]
            for k in keys:
                self._data.pop(k, None)
            return len(keys)

    def incr(self, key: str, amount: int = 1, ttl: int = 0) -> int:
        with self._lock:
            current = int(self.get(key) or 0) + amount
            self.set(key, str(current), ttl)
            return current


class Cache:
    def __init__(self) -> None:
        self._client = None
        self._memory = _MemoryCache()
        self._mode = "memory"
        if settings.REDIS_ENABLED:
            try:
                import redis  # 延迟导入，未装也能跑

                client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True,
                                              socket_connect_timeout=2, socket_timeout=2)
                client.ping()
                self._client = client
                self._mode = "redis"
            except Exception as exc:  # pragma: no cover - 环境相关
                logger.warning("Redis 不可用（%s），回退进程内缓存", exc)

    # ── 基础操作 ──
    @property
    def mode(self) -> str:
        return self._mode

    def get(self, key: str) -> Any | None:
        raw = self._client.get(key) if self._client else self._memory.get(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return raw

    def set(self, key: str, value: Any, ttl: int | None = None) -> None:
        ttl = settings.CACHE_TTL if ttl is None else ttl
        raw = json.dumps(value, ensure_ascii=False, default=str)
        if self._client:
            self._client.set(key, raw, ex=ttl or None)
        else:
            self._memory.set(key, raw, ttl)

    def delete(self, key: str) -> None:
        if self._client:
            self._client.delete(key)
        else:
            self._memory.delete(key)

    def delete_prefix(self, prefix: str) -> int:
        if self._client:
            keys = list(self._client.scan_iter(match=f"{prefix}*", count=500))
            return int(self._client.delete(*keys)) if keys else 0
        return self._memory.delete_prefix(prefix)

    def incr(self, key: str, amount: int = 1, ttl: int = 0) -> int:
        if self._client:
            value = int(self._client.incrby(key, amount))
            if ttl:
                self._client.expire(key, ttl)
            return value
        return self._memory.incr(key, amount, ttl)

    def get_or_set(self, key: str, producer: Callable[[], Any], ttl: int | None = None) -> Any:
        cached = self.get(key)
        if cached is not None:
            return cached
        value = producer()
        self.set(key, value, ttl)
        return value

    def health(self) -> dict:
        if not self._client:
            return {"mode": "memory", "ok": True, "detail": "Redis 未启用或不可用，已降级为进程内缓存"}
        try:
            self._client.ping()
            return {"mode": "redis", "ok": True, "detail": settings.REDIS_URL}
        except Exception as exc:  # pragma: no cover
            return {"mode": "redis", "ok": False, "detail": str(exc)}


cache = Cache()
