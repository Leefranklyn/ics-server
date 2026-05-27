from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_db, require_role
from ics_backend.schemas.room import TimeWindowsUpdate
from ics_backend.schemas.user import AdminCardCreate, CardStatusUpdate, RegistrationStartRequest, RegistrationStartResponse, UserCreateResponse, UserPage
from ics_backend.services.attendance import update_room_windows
from ics_backend.services.card import create_card_user, list_users, update_card_status
from ics_backend.services.registration import clear_registration_session, get_pending_session, start_registration_session


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


@router.post("/registration/start", response_model=RegistrationStartResponse)
async def start_registration(payload: RegistrationStartRequest) -> RegistrationStartResponse:
    """Start a card registration session from the web portal.
    The ESP32 will poll /api/registration/status and submit the UID when a card is tapped."""
    session_id = start_registration_session(
        full_name=payload.full_name,
        email=payload.email,
        role=payload.role,
        matric_number=payload.matric_number,
        department=payload.department,
        level=payload.level,
        assigned_rooms=[str(r) for r in (payload.assigned_rooms or [])],
    )
    return RegistrationStartResponse(session_id=session_id)


@router.get("/registration/status")
async def admin_registration_status() -> dict[str, object]:
    """Poll the registration session status from the web portal.
    
    Returns:
    - active: Whether a registration session is active
    - completed: Whether the card has been tapped and user created
    - received_uid: The card UID that was tapped (only if completed=true)
    - full_name: The user being registered (only if active=true)
    - session_id: The registration session ID (only if active=true)
    """
    session = get_pending_session()
    if session is None:
        return {"active": False, "completed": False}
    return {
        "active": True,
        "completed": session.completed,
        "session_id": session.session_id,
        "full_name": session.full_name,
        "received_uid": session.received_uid,
    }


@router.delete("/registration")
async def cancel_registration() -> dict[str, str]:
    """Cancel any active registration session."""
    clear_registration_session()
    return {"status": "ok"}
