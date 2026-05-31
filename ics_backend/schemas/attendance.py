from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AttendanceSessionStartRequest(BaseModel):
    room_id: UUID
    course_id: UUID
    session_name: str | None = Field(default=None, max_length=255)


class AttendanceSessionStartResponse(BaseModel):
    session_id: UUID
    room_id: UUID
    course_id: UUID
    started_at: datetime
    status: Literal["active"]


class AttendanceSessionEndResponse(BaseModel):
    session_id: UUID
    ended_at: datetime | None
    status: Literal["closed"]
    total_marked: int


class AttendanceSessionActiveResponse(BaseModel):
    session_id: UUID | None = None
    room_id: UUID | None = None
    course_id: UUID | None = None
    started_at: datetime | None = None
    status: Literal["active", "none"]
    marked_count: int | None = None
