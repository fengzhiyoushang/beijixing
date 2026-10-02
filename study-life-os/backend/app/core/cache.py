"""缓存抽象层：Redis 优先，连接失败透明回退进程内 TTL 缓存。

键规范（见技术方案 §9）：
    sl:dashboard:{uid}   仪表盘聚合   TTL 60s
    sl:ai:ctx:{sid}      AI 会话上下文 TTL 1h
    sl:streak:{uid}      打卡连续天数  TTL 当日
"""
import json
import time
from typing import Any, Callable, Optional

from app.core.config import settings


class _MemoryBackend:
    def __init__(self) -> None:
        self._store: dict[str, tuple[str, Optional[float]]] = {}

    def get(self, key: str) -> Optional[str]:
        item = self._store.get(key)
        if not item:
            return None
        value, expire = item
        if expire is not None and time.time() > expire:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        expire = time.time() + ttl if ttl else None
        self._store[key] = (value, expire)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)


class Cache:
    """对外统一接口，JSON 值自动序列化。"""

    def __init__(self) -> None:
        self._mem = _MemoryBackend()
        self._redis = None
        if settings.REDIS_ENABLED:
            try:
                import redis  # 延迟导入，未安装也不报错

                client = redis.from_url(
                    settings.REDIS_URL,
                    socket_connect_timeout=1,
                    socket_timeout=1,
                    decode_responses=True,
                )
                client.ping()
                self._redis = client
            except Exception:
                self._redis = None

    @property
    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    # ---------- 原始字符串 ----------
    def _get_raw(self, key: str) -> Optional[str]:
        if self._redis:
            try:
                return self._redis.get(key)
            except Exception:
                return self._mem.get(key)
        return self._mem.get(key)

    def _set_raw(self, key: str, value: str, ttl: Optional[int]) -> None:
        if self._redis:
            try:
                if ttl:
                    self._redis.set(key, value, ex=ttl)
                else:
                    self._redis.set(key, value)
                return
            except Exception:
                pass
        self._mem.set(key, value, ttl)

    # ---------- JSON ----------
    def get_json(self, key: str) -> Optional[Any]:
        raw = self._get_raw(key)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def set_json(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._set_raw(key, json.dumps(value, ensure_ascii=False, default=str), ttl)

    def delete(self, key: str) -> None:
        if self._redis:
            try:
                self._redis.delete(key)
            except Exception:
                pass
        self._mem.delete(key)

    def get_or_set(self, key: str, ttl: int, producer: Callable[[], Any]) -> Any:
        hit = self.get_json(key)
        if hit is not None:
            return hit
        value = producer()
        self.set_json(key, value, ttl)
        return value


cache = Cache()
