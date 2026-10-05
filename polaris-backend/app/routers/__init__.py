"""路由聚合：统一挂载到 /api/v1。"""
from fastapi import APIRouter

from app.routers import (ai, auth, bookmarks, classroom, courses, dashboard, finance, health,
                         kaoyan, knowledge, news, pdf_schedule, study, system, tasks, wechat)

api_router = APIRouter()
api_router.include_router(dashboard.router)
api_router.include_router(auth.router)
api_router.include_router(courses.router)
api_router.include_router(tasks.router)
api_router.include_router(classroom.router)
api_router.include_router(pdf_schedule.router)
api_router.include_router(study.router)
api_router.include_router(kaoyan.router)
api_router.include_router(knowledge.router)
api_router.include_router(finance.router)
api_router.include_router(health.router)
api_router.include_router(system.router)
api_router.include_router(wechat.router)
api_router.include_router(ai.router)
api_router.include_router(bookmarks.router)
api_router.include_router(news.router)

__all__ = ["api_router"]
