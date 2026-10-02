"""全部 SQLAlchemy 模型统一注册。"""
from app.models.user import User
from app.models.course import Course, ClassSlot
from app.models.task import Task
from app.models.classroom import ClassroomRecord
from app.models.checkin import CheckinRecord
from app.models.kaoyan import KaoyanGoal, PlanPhase, PlanTask
from app.models.knowledge import KnowledgeDoc, KnowledgeChunk
from app.models.finance import FinanceRecord, Budget
from app.models.health import HealthLog, HealthSetting
from app.models.aimodel import AiSession, AiMessage

__all__ = [
    "User",
    "Course", "ClassSlot",
    "Task",
    "ClassroomRecord",
    "CheckinRecord",
    "KaoyanGoal", "PlanPhase", "PlanTask",
    "KnowledgeDoc", "KnowledgeChunk",
    "FinanceRecord", "Budget",
    "HealthLog", "HealthSetting",
    "AiSession", "AiMessage",
]
