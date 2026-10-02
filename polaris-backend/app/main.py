"""北极星 · 个人战略终端 —— FastAPI 应用入口。

包含：CORS、统一异常处理、路由挂载、静态文件、接口文档、启动初始化。
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.cache import cache
from app.core.config import settings
from app.core.database import init_db, server_status
from app.core.exceptions import register_exception_handlers
from app.routers import api_router

logging.basicConfig(
    level=logging.DEBUG if settings.DEBUG else logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
logger = logging.getLogger("polaris")


async def _reminder_loop() -> None:
    """可选的进程内提醒扫描（生产更推荐 cron / 云托管定时触发器）。"""
    from app.core.database import session_scope
    from app.services import wechat_service

    interval = max(1, settings.WX_PUSH_INTERVAL_MIN) * 60
    logger.info("提醒扫描已启动：每 %s 分钟一次", settings.WX_PUSH_INTERVAL_MIN)
    while True:
        try:
            with session_scope() as db:
                result = await wechat_service.run_scan(db)
            logger.info("提醒扫描：DDL %s 条、上课 %s 条",
                        result["ddl"]["sent"], result["class"]["sent"])
        except asyncio.CancelledError:            # pragma: no cover
            raise
        except Exception:                         # pragma: no cover
            logger.exception("提醒扫描失败")
        await asyncio.sleep(interval)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("启动 %s v%s", settings.APP_NAME, settings.APP_VERSION)
    try:
        init_db()
        status = server_status()
        logger.info("数据库就绪：engine=%s backend=%s", status["engine"], status["backend"])
        if status["engine"] == "sqlite" and settings.DB_BACKEND.lower() == "mysql":
            logger.warning("MySQL 不可用，已自动回退 SQLite（数据文件见 SQLITE_PATH）")
    except Exception as exc:                     # pragma: no cover
        logger.exception("初始化数据库失败：%s", exc)
    logger.info("缓存模式：%s | AI 模式：%s | 微信推送：%s", cache.mode,
                "live" if settings.deepseek_configured else "mock（未配置 DEEPSEEK_API_KEY）",
                "live" if settings.wechat_configured else "mock（未配置 WX_APPID/WX_APP_SECRET）")

    reminder_task = asyncio.create_task(_reminder_loop()) if settings.WX_SCHEDULER_ENABLED else None
    if reminder_task:
        logger.info("进程内提醒调度已开启（WX_SCHEDULER_ENABLED=true）")
    try:
        yield
    finally:
        if reminder_task:
            reminder_task.cancel()
        logger.info("应用关闭")


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "北极星 · 个人战略终端后端：课程表 / DDL 任务 / 空教室 / 学习记录 / 考研规划 / "
        "知识库 RAG / 财务 / 健康 / AI 助手（Function Call） / 系统管理。\n\n"
        "- 认证：`POST /api/v1/auth/login` 获取 JWT，之后请求头携带 `Authorization: Bearer <token>`\n"
        "- 降级策略：MySQL→SQLite、Redis→进程内缓存、DeepSeek→演示模式，均可开箱运行"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

# ── 异常处理 ──
register_exception_handlers(app)

# ── 路由 ──
app.include_router(api_router, prefix=settings.API_PREFIX)

# ── 静态文件（上传的图片/文档） ──
_upload_dir = Path(settings.upload_path)
app.mount("/uploads", StaticFiles(directory=str(_upload_dir)), name="uploads")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health", tags=["系统管理"], summary="健康检查")
def health() -> dict:
    from app.ai.deepseek import deepseek

    db_status = server_status()
    return {
        "status": "ok" if db_status["ok"] else "degraded",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "database": db_status,
        "cache": cache.health(),
        "ai": deepseek.status(),
    }


@app.exception_handler(404)
async def not_found(_request, exc):             # pragma: no cover
    return JSONResponse(status_code=404, content={"code": "not_found", "message": "接口不存在"})


if __name__ == "__main__":                       # pragma: no cover
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.DEBUG)
