from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


UserRole = Literal["student", "staff", "admin"]
CardStatus = Literal["active", "suspended"]


class AdminCardCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    matric_number: str | None = Field(default=None, max_length=50)
    role: UserRole
    raw_card_uid: str = Field(min_length=1, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    level: int | None = None
    assigned_rooms: list[UUID] = Field(default_factory=list)


class CardStatusUpdate(BaseModel):
    status: CardStatus


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    full_name: str
    email: str
    matric_number: str | None
    role: str
    card_status: str
    department: str | None
    level: int | None
    assigned_rooms: list[UUID | str]
    created_at: datetime


class UserCreateResponse(BaseModel):
    user_id: UUID


class UserPage(BaseModel):
    page: int
    limit: int
    total: int
    items: list[UserPublic]


class RegistrationStartRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=3, max_length=255)
    role: UserRole
    matric_number: str | None = Field(default=None, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    level: int | None = None
    assigned_rooms: list[UUID] = Field(default_factory=list)


class RegistrationStartResponse(BaseModel):
    session_id: str
    status: str = "ok"
