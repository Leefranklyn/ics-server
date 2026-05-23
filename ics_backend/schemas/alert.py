from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    alert_id: UUID
    room_id: UUID
    alert_type: str
    severity: Literal["warning", "critical"]
    message: str
    acknowledged: bool
    triggered_at: datetime


class AlertAcknowledgeResponse(BaseModel):
    alert_id: UUID
    acknowledged: bool
