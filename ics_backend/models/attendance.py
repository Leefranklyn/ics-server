from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ics_backend.database import Base


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'closed')", name="attendance_session_status_valid"),
        Index("ix_attendance_sessions_room_status", "room_id", "status"),
        Index("ix_attendance_sessions_course_started_at", "course_id", "started_at"),
        Index("uq_attendance_sessions_active_room", "room_id", unique=True, postgresql_where=text("status = 'active'")),
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.course_id"), nullable=False)
    opened_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    session_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))

    room = relationship("Room", back_populates="attendance_sessions")
    course = relationship("Course", back_populates="attendance_sessions")
    opener = relationship("User", back_populates="opened_attendance_sessions")
    records = relationship("AttendanceRecord", back_populates="session")


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("session_id", "user_id", name="uq_attendance_records_session_user"),
        Index("ix_attendance_records_session_marked_at", "session_id", "marked_at"),
        Index("ix_attendance_records_room_marked_at", "room_id", "marked_at"),
        Index("ix_attendance_records_course_marked_at", "course_id", "marked_at"),
        Index("ix_attendance_records_user_marked_at", "user_id", "marked_at"),
    )

    attendance_record_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attendance_sessions.session_id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("courses.course_id"), nullable=False)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    marked_by_card_uid: Mapped[str] = mapped_column(String(50), nullable=False)

    session = relationship("AttendanceSession", back_populates="records")
    user = relationship("User", back_populates="attendance_records")
    room = relationship("Room", back_populates="attendance_records")
    course = relationship("Course", back_populates="attendance_records")
