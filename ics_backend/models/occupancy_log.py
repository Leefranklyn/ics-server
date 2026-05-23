from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ics_backend.database import Base


class OccupancyLog(Base):
    __tablename__ = "occupancy_log"
    __table_args__ = (Index("ix_occupancy_log_room_timestamp", "room_id", "timestamp"),)

    occ_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )
    room_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.room_id"), nullable=False)
    occupancy_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ac_setpoint: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    room = relationship("Room", back_populates="occupancy_logs")
