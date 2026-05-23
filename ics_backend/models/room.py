from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import CheckConstraint, Integer, String, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ics_backend.database import Base


class Room(Base):
    __tablename__ = "rooms"
    __table_args__ = (CheckConstraint("lock_state IN ('locked', 'unlocked')", name="lock_state_valid"),)

    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    room_name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    assigned_staff: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    lock_state: Mapped[str] = mapped_column(String(20), nullable=False, server_default=text("'locked'"))
    current_occupancy: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    ac_setpoint: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("24"))
    time_windows: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )

    courses = relationship("Course", back_populates="room")
    access_logs = relationship("AccessLog", back_populates="room")
    occupancy_logs = relationship("OccupancyLog", back_populates="room")
    environment_logs = relationship("EnvironmentLog", back_populates="room")
    alerts = relationship("Alert", back_populates="room")
