"""模型注册中心：导入全部 ORM 模型（建表与关系解析依赖此处）。"""
from app.models.ai import AiMessage, AiSession
from app.models.classroom import Classroom, ClassroomStatusLog, ClassroomUsageRecord
from app.models.course import Course, CourseSchedule, Semester
from app.models.finance import FinanceBudget, FinanceRecord
from app.models.health import HealthRecord, HealthSetting
from app.models.kaoyan import KaoyanPlanPhase, KaoyanPlanTask, KaoyanTarget
from app.models.knowledge import KnowledgeChunk, KnowledgeDoc, KnowledgeFolder
from app.models.pdf_schedule import PdfScheduleEntry, PdfScheduleUpload
from app.models.study import StudyRecord
from app.models.system import DataBackup, SystemConfig
from app.models.task import DdlTask, SubTask
from app.models.user import User
from app.models.wechat import WxPushLog, WxSubscriptionQuota

__all__ = [
    # ① 用户
    "User",
    # ② 课程
    "Semester", "Course", "CourseSchedule",
    # ③ DDL 任务
    "DdlTask", "SubTask",
    # ④⑤ 教室
    "Classroom", "ClassroomStatusLog", "ClassroomUsageRecord",
    # ⑭ PDF 教室课表
    "PdfScheduleUpload", "PdfScheduleEntry",
    # ⑥ 学习记录
    "StudyRecord",
    # ⑦ 考研
    "KaoyanTarget", "KaoyanPlanPhase", "KaoyanPlanTask",
    # ⑧ 知识库
    "KnowledgeFolder", "KnowledgeDoc", "KnowledgeChunk",
    # ⑨ 财务
    "FinanceRecord", "FinanceBudget",
    # ⑩ 健康
    "HealthRecord", "HealthSetting",
    # AI 会话
    "AiSession", "AiMessage",
    # 系统管理
    "DataBackup", "SystemConfig",
    # 微信订阅消息
    "WxSubscriptionQuota", "WxPushLog",
]

# 备份 / 统计用的表清单
ALL_TABLES = [
    "users", "semesters", "courses", "course_schedules",
    "ddl_tasks", "subtasks",
    "classrooms", "classroom_status_logs",
    "pdf_schedule_uploads", "pdf_schedule_entries",
    "study_records",
    "kaoyan_targets", "kaoyan_plan_phases", "kaoyan_plan_tasks",
    "knowledge_folders", "knowledge_docs", "knowledge_chunks",
    "finance_records", "finance_budgets",
    "health_records", "health_settings",
    "ai_sessions", "ai_messages",
    "data_backups", "system_configs",
    "wx_subscription_quotas", "wx_push_logs",
]
