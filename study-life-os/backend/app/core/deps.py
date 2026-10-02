"""FastAPI 依赖注入：get_db / get_current_user。"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)

_credentials_exception = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="未登录或凭证已过期",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if cred is None or not cred.credentials:
        raise _credentials_exception
    payload = decode_access_token(cred.credentials)
    if not payload or not payload.get("sub"):
        raise _credentials_exception
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise _credentials_exception
    return user
