from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_db, require_role
from ics_backend.models.user import User
from ics_backend.schemas.room import DashboardRoomResponse
from ics_backend.services.attendance import get_dashboard_room


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/rooms/{room_id}", response_model=DashboardRoomResponse)
async def dashboard_room(
    room_id: UUID,
    current_user: User = Depends(require_role("staff", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return await get_dashboard_room(db, current_user, room_id)
