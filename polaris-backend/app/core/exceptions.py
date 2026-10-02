"""统一异常与全局异常处理器。"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = logging.getLogger("polaris.error")


class AppError(Exception):
    """业务异常：路由/服务层抛出，由处理器统一转为结构化 JSON。"""

    def __init__(self, message: str, *, code: str = "bad_request",
                 status_code: int = status.HTTP_400_BAD_REQUEST, detail: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.detail = detail or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "资源不存在", **kw):
        super().__init__(message, code="not_found", status_code=status.HTTP_404_NOT_FOUND, **kw)


class AuthError(AppError):
    def __init__(self, message: str = "未认证或凭证已失效", **kw):
        super().__init__(message, code="unauthorized", status_code=status.HTTP_401_UNAUTHORIZED, **kw)


class PermissionError_(AppError):
    def __init__(self, message: str = "无权访问该资源", **kw):
        super().__init__(message, code="forbidden", status_code=status.HTTP_403_FORBIDDEN, **kw)


class ConflictError(AppError):
    def __init__(self, message: str = "资源冲突", **kw):
        super().__init__(message, code="conflict", status_code=status.HTTP_409_CONFLICT, **kw)


def _payload(code: str, message: str, detail: dict | None = None) -> dict:
    body = {"code": code, "message": message}
    if detail:
        body["detail"] = detail
    return body


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_payload(exc.code, exc.message, exc.detail))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = [
            {"field": ".".join(str(x) for x in e.get("loc", [])), "msg": e.get("msg", "")}
            for e in exc.errors()
        ]
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_payload("validation_error", "请求参数校验失败", {"errors": errors}),
        )

    @app.exception_handler(IntegrityError)
    async def _integrity(_: Request, exc: IntegrityError):
        logger.warning("数据库约束冲突：%s", exc)
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=_payload("integrity_error", "数据冲突（唯一键或外键约束）", {"raw": str(exc.orig)[:200]}),
        )

    @app.exception_handler(SQLAlchemyError)
    async def _sqlalchemy(_: Request, exc: SQLAlchemyError):
        logger.exception("数据库错误")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("database_error", "数据库操作失败", {"raw": str(exc)[:200]}),
        )

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception):
        logger.exception("未捕获异常")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_payload("internal_error", "服务内部错误", {"raw": str(exc)[:200]}),
        )
