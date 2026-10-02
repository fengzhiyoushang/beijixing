"""StudyLifeOS 后端入口。

启动：uvicorn app.main:app --reload --port 8000
文档：http://localhost:8000/docs
"""
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.cache import cache
from app.core.config import settings
from app.core.database import init_db
from app.routers import api_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version="0.1.0",
        description="个人学习·工作·生活管理终端统一后端：Web 管理端 + 微信小程序 + DeepSeek AI 全链路。",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 上传文件静态服务（目录必须存在）
    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["系统"])
    def health():
        from app.services import deepseek
        return {
            "status": "ok",
            "app": settings.APP_NAME,
            "db": settings.DB_BACKEND,
            "cache": cache.backend,
            "ai": "deepseek" if deepseek.is_configured() else "mock",
        }

    return app


app = create_app()
