from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel

from ics_backend.schemas.access import RecentAccessEvent


class RoomConfigResponse(BaseModel):
    room_id: UUID
    capacity: int
    time_windows: dict[str, Any]
    ac_setpoint: int
    lock_state: str
    current_occupancy: int


class TimeWindowsUpdate(BaseModel):
    time_windows: dict[str, Any]


class DashboardRoomResponse(BaseModel):
    room_id: UUID
    room_name: str
    current_occupancy: int
    capacity: int
    lock_state: str
    ac_setpoint: int
    temperature: float | None
    humidity: float | None
    recent_events: list[RecentAccessEvent]
