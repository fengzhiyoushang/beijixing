"""v1 API 路由聚合。"""
from fastapi import APIRouter

from app.routers import (
    ai,
    auth,
    checkin,
    classroom,
    courses,
    dashboard,
    finance,
    health,
    kaoyan,
    knowledge,
    tasks,
)

api_router = APIRouter()
for module in (auth, courses, tasks, checkin, classroom, kaoyan,
               knowledge, finance, health, dashboard, ai):
    api_router.include_router(module.router)
