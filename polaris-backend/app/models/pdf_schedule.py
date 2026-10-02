"""PDF 教室课表：上传记录 + 解析条目。"""
from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, iso


class PdfScheduleUpload(Base, TimestampMixin):
    """一次 PDF 上传的解析记录（状态、置信度、错误与建议）。"""

    __tablename__ = "pdf_schedule_uploads"
    __table_args__ = (
        Index("ix_psu_user", "user_id", "created_at"),
        {"comment": "PDF 课表上传记录表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(255), comment="原始文件名")
    stored_path: Mapped[str | None] = mapped_column(String(512), default=None, comment="落盘路径")
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    room_no: Mapped[str | None] = mapped_column(String(64), default=None, comment="课表所属教室")
    semester: Mapped[str | None] = mapped_column(String(64), default=None, comment="如 2026-2027学年第一学期")
    parse_mode: Mapped[str | None] = mapped_column(String(24), default=None,
                                                   comment="table_grid|table_list|vision|text")
    status: Mapped[str] = mapped_column(String(16), default="parsed",
                                        comment="parsed|partial|failed")
    error: Mapped[str | None] = mapped_column(Text, default=None, comment="失败原因")
    suggestions: Mapped[str | None] = mapped_column(Text, default=None, comment="处理建议（JSON 数组）")
    entry_count: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, comment="解析置信度 0~1")

    entries: Mapped[list["PdfScheduleEntry"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", lazy="selectin")

    def to_dict(self, with_entries: bool = False) -> dict:
        import json as _json

        data = {
            "id": self.id,
            "filename": self.filename,
            "file_size": self.file_size,
            "room_no": self.room_no,
            "semester": self.semester,
            "parse_mode": self.parse_mode,
            "status": self.status,
            "status_label": {"parsed": "解析成功", "partial": "部分成功", "failed": "解析失败"}.get(self.status),
            "error": self.error,
            "suggestions": _json.loads(self.suggestions) if self.suggestions else [],
            "entry_count": self.entry_count,
            "confidence": round(self.confidence or 0, 3),
            "created_at": iso(self.created_at),
        }
        if with_entries:
            data["entries"] = [e.to_dict() for e in self.entries]
        return data


class PdfScheduleEntry(Base, TimestampMixin):
    """解析出的单条课程安排（结构化存储，可按教室/星期/课程筛选）。"""

    __tablename__ = "pdf_schedule_entries"
    __table_args__ = (
        Index("ix_pse_upload", "upload_id"),
        Index("ix_pse_room_weekday", "room_no", "weekday"),
        {"comment": "PDF 课表解析条目表"},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    upload_id: Mapped[int] = mapped_column(
        ForeignKey("pdf_schedule_uploads.id", ondelete="CASCADE"), index=True)

    course_name: Mapped[str] = mapped_column(String(128), comment="课程名称")
    teacher: Mapped[str | None] = mapped_column(String(64), default=None)
    class_name: Mapped[str | None] = mapped_column(String(128), default=None, comment="班级/教学班")
    course_code: Mapped[str | None] = mapped_column(String(32), default=None, comment="课程号")
    weekday: Mapped[int] = mapped_column(Integer, comment="1=周一 … 7=周日")
    start_section: Mapped[int] = mapped_column(Integer, default=1)
    end_section: Mapped[int] = mapped_column(Integer, default=2)
    start_time: Mapped[str] = mapped_column(String(5), default="08:00")
    end_time: Mapped[str] = mapped_column(String(5), default="09:40")
    weeks: Mapped[str] = mapped_column(String(64), default="1-16")
    week_type: Mapped[str] = mapped_column(String(8), default="全周")
    location: Mapped[str | None] = mapped_column(String(128), default=None, comment="地点全称")
    room_no: Mapped[str | None] = mapped_column(String(64), default=None, comment="教室编号")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    upload: Mapped[PdfScheduleUpload] = relationship(back_populates="entries")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "upload_id": self.upload_id,
            "course_name": self.course_name,
            "teacher": self.teacher,
            "class_name": self.class_name,
            "course_code": self.course_code,
            "weekday": self.weekday,
            "weekday_cn": ["周一", "周二", "周三", "周四", "周五", "周六", "周日"][self.weekday - 1],
            "start_section": self.start_section,
            "end_section": self.end_section,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "weeks": self.weeks,
            "week_type": self.week_type,
            "location": self.location,
            "room_no": self.room_no,
            "confidence": round(self.confidence or 0, 3),
        }
