from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_db, require_role
from ics_backend.schemas.room import TimeWindowsUpdate
from ics_backend.schemas.user import AdminCardCreate, CardStatusUpdate, UserCreateResponse, UserPage
from ics_backend.services.attendance import update_room_windows
from ics_backend.services.card import create_card_user, list_users, update_card_status


router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_role("admin"))])


@router.post("/cards", response_model=UserCreateResponse)
async def create_card(payload: AdminCardCreate, db: AsyncSession = Depends(get_db)) -> UserCreateResponse:
    user_id = await create_card_user(db, payload)
    return UserCreateResponse(user_id=user_id)


@router.put("/cards/{user_id}/status")
async def set_card_status(user_id: UUID, payload: CardStatusUpdate, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await update_card_status(db, user_id, payload.status)
    return {"status": "ok"}


@router.put("/rooms/{room_id}/windows")
async def set_room_windows(
    room_id: UUID, payload: TimeWindowsUpdate, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    await update_room_windows(db, room_id, payload.time_windows)
    return {"status": "ok"}


@router.get("/users", response_model=UserPage)
async def admin_users(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
) -> UserPage:
    total, users = await list_users(db, page, limit)
    return UserPage(page=page, limit=limit, total=total, items=users)
