from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class EnvironmentEventCreate(BaseModel):
    room_id: UUID
    temperature: float
    humidity: float
    light_level: int
    ac_setpoint: int
    timestamp: datetime


class EnvironmentEventResponse(BaseModel):
    status: str = "ok"


class EnergyAnalyticsResponse(BaseModel):
    room_id: UUID
    date_from: datetime
    date_to: datetime
    runtime_hours: float
    estimated_kwh: float
    avg_temperature: float | None
    avg_humidity: float | None
