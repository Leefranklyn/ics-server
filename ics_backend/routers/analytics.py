from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_current_user, get_db, require_role
from ics_backend.models.user import User
from ics_backend.schemas.alert import AlertAcknowledgeResponse, AlertResponse
from ics_backend.schemas.environment import EnergyAnalyticsResponse
from ics_backend.services.alerts import acknowledge_alert, list_alerts
from ics_backend.services.attendance import get_energy_analytics


router = APIRouter(prefix="/api", tags=["analytics"])


@router.get("/analytics/energy/{room_id}", response_model=EnergyAnalyticsResponse)
async def energy_analytics(
    room_id: UUID,
    date_from: datetime,
    date_to: datetime,
    current_user: User = Depends(require_role("staff", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return await get_energy_analytics(db, current_user, room_id, date_from, date_to)


@router.get("/alerts", response_model=list[AlertResponse])
async def alerts(
    acknowledged: bool | None = None,
    room_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[object]:
    return await list_alerts(db, current_user, acknowledged, room_id)


@router.put("/alerts/{alert_id}/acknowledge", response_model=AlertAcknowledgeResponse)
async def acknowledge(
    alert_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AlertAcknowledgeResponse:
    alert = await acknowledge_alert(db, current_user, alert_id)
    return AlertAcknowledgeResponse(alert_id=alert.alert_id, acknowledged=alert.acknowledged)
