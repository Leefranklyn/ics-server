from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, DateTime, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ics_backend.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role IN ('student', 'staff', 'admin')", name="role_valid"),
        CheckConstraint("card_status IN ('active', 'suspended')", name="card_status_valid"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    matric_number: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    card_uid_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    card_uid_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    card_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'active'"))
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    assigned_rooms: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()")
    )

    lectured_courses = relationship("Course", back_populates="lecturer")
    enrollments = relationship("Enrollment", back_populates="student")
    access_logs = relationship("AccessLog", back_populates="user")
    opened_attendance_sessions = relationship("AttendanceSession", back_populates="opener")
    attendance_records = relationship("AttendanceRecord", back_populates="user")
