"""安全层：密码哈希（PBKDF2-HMAC-SHA256）与 JWT 签发/校验。

不引入 C 扩展依赖（passlib/bcrypt 均可省），保证任意 Python 环境可装。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta, timezone

import jwt

from app.core.config import settings

_ALGO = "pbkdf2_sha256"
_ITERATIONS = 260_000


def hash_password(password: str, *, iterations: int = _ITERATIONS) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return "$".join([
        _ALGO,
        str(iterations),
        base64.b64encode(salt).decode(),
        base64.b64encode(digest).decode(),
    ])


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, iterations, salt_b64, digest_b64 = stored.split("$")
        if algo != _ALGO:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


def needs_rehash(stored: str | None) -> bool:
    if not stored:
        return True
    try:
        return int(stored.split("$")[1]) < _ITERATIONS
    except Exception:
        return True


def create_access_token(subject: str | int, extra: dict | None = None,
                        expires_minutes: int | None = None) -> str:
    now = datetime.now(timezone.utc)
    minutes = expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    payload = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "iss": settings.APP_NAME,
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


def derive_wx_openid(code: str) -> str:
    """开发模式：由 code 派生稳定 openid（生产替换为微信 code2session 调用）。"""
    h = hashlib.sha1(f"polaris::{code}".encode("utf-8")).hexdigest()
    return f"dev_{h[:24]}"
