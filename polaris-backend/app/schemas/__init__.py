"""Pydantic 出入参模型统一出口。"""
from app.schemas.ai import ChatIn, ToolCallIn
from app.schemas.auth import (LoginIn, PasswordChangeIn, RegisterIn, TokenOut, UserConfigIn,
                             UserOut, UserUpdateIn, WxBindIn, WxLoginIn)
from app.schemas.classroom import (ClassroomIn, ClassroomUpdate, StatusReportIn, VisionRecognizeIn)
from app.schemas.course import (CourseImportIn, CourseIn, CourseUpdate, ScheduleIn, SemesterIn,
                                SemesterUpdate)
from app.schemas.finance import BudgetIn, BudgetUpdate, FinanceRecordIn, FinanceRecordUpdate
from app.schemas.health import HealthRecordIn, HealthRecordUpdate, HealthSettingIn, HeartbeatIn
from app.schemas.kaoyan import (KaoyanTargetIn, KaoyanTargetUpdate, PhaseIn, PhaseUpdate,
                                PlanGenerateIn, PlanTaskIn, PlanTaskUpdate, ScoreIn, SubjectScoreIn)
from app.schemas.knowledge import DocIn, DocUpdate, FolderIn, FolderUpdate, QaIn
from app.schemas.study import MockScoreIn, StudyRecordIn, StudyRecordUpdate
from app.schemas.system import BackupIn, ConfigIn, ConfigUpdate
from app.schemas.task import SubTaskIn, SubTaskUpdate, TaskIn, TaskUpdate

__all__ = [name for name in dir() if name.endswith(("In", "Out", "Update")) or name in {
    "SubjectScoreIn", "ChatIn", "ToolCallIn", "HeartbeatIn",
}]
