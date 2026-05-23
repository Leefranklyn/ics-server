from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ics_backend.database import Base


class Course(Base):
    __tablename__ = "courses"

    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    course_code: Mapped[str] = mapped_column(String(20), nullable=False)
    course_name: Mapped[str] = mapped_column(String(255), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    lecturer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=False)
    schedule: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    semester: Mapped[str | None] = mapped_column(String(30), nullable=True)
    academic_year: Mapped[str | None] = mapped_column(String(20), nullable=True)

    room = relationship("Room", back_populates="courses")
    lecturer = relationship("User", back_populates="lectured_courses")
    enrollments = relationship("Enrollment", back_populates="course")
    access_logs = relationship("AccessLog", back_populates="course")
