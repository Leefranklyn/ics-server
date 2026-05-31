from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AccessEventCreate(BaseModel):
    room_id: UUID
    card_uid: str = Field(min_length=1, max_length=50)
    reader: Literal["entry", "exit"]
    timestamp: datetime


class AccessEventResponse(BaseModel):
    decision: Literal["granted", "denied"]
    message: str


class EspUserCompact(BaseModel):
    uid_fast: str
    user_id: UUID
    role: str
    name: str


class RegistrationStatusResponse(BaseModel):
    active: bool
    session_id: str | None = None


class RegistrationUidCreate(BaseModel):
    uid: str = Field(min_length=1, max_length=50)


class RegistrationUidResponse(BaseModel):
    status: str = "ok"
    message: str = "Card registered"


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
    session_id: UUID
    session_name: str | None
    session_started_at: datetime
    event_type: str
    marked_at: datetime
