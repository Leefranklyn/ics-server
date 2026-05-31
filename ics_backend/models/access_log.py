from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ics_backend.database import Base


class AccessLog(Base):
    __tablename__ = "access_log"
    __table_args__ = (
        CheckConstraint("event_type IN ('entry', 'exit', 'denied', 'attendance')", name="event_type_valid"),
        CheckConstraint("door_state IN ('opened', 'closed')", name="door_state_valid"),
        Index("ix_access_log_room_timestamp", "room_id", "timestamp"),
        Index("ix_access_log_user_timestamp", "user_id", "timestamp"),
        Index("ix_access_log_course_timestamp", "course_id", "timestamp"),
    )

    log_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.user_id"), nullable=True)
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.course_id"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    card_uid: Mapped[str] = mapped_column(String(50), nullable=False)
    door_state: Mapped[str] = mapped_column(String(20), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("NOW()"))

    user = relationship("User", back_populates="access_logs")
    room = relationship("Room", back_populates="access_logs")
    course = relationship("Course", back_populates="access_logs")
