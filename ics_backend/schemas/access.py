from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AccessEventCreate(BaseModel):
    room_id: UUID
    card_uid: str = Field(min_length=1, max_length=50)
    event_type: Literal["entry", "exit", "denied"]
    door_state: Literal["opened", "closed"]
    timestamp: datetime


class AccessEventResponse(BaseModel):
    log_id: UUID
    status: str = "ok"


class EspUserCompact(BaseModel):
    card_uid_hash: str
    user_id: UUID
    role: str
    enrolled_rooms: list[UUID | str]


class RecentAccessEvent(BaseModel):
    full_name: str | None
    matric_number: str | None
    event_type: str
    timestamp: datetime
    door_state: str


class AttendanceReportRow(BaseModel):
    timestamp: datetime
    full_name: str | None
    matric_number: str | None
    course_code: str | None
    course_name: str | None
    event_type: str
    door_state: str
