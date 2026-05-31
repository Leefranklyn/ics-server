from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_db, require_role
from ics_backend.models.user import User
from ics_backend.schemas.attendance import (
    AttendanceSessionActiveResponse,
    AttendanceSessionEndResponse,
    AttendanceSessionStartRequest,
    AttendanceSessionStartResponse,
)
from ics_backend.services.attendance import (
    end_attendance_session,
    get_active_attendance_session_for_room,
    start_attendance_session,
)


router = APIRouter(prefix="/api/admin/attendance/session", tags=["attendance sessions"])


@router.post("/start", response_model=AttendanceSessionStartResponse)
async def start_session(
    payload: AttendanceSessionStartRequest,
    current_user: User = Depends(require_role("staff", "admin")),
    db: AsyncSession = Depends(get_db),
) -> AttendanceSessionStartResponse:
    session = await start_attendance_session(db, current_user, payload)
    return AttendanceSessionStartResponse(
        session_id=session.session_id,
        room_id=session.room_id,
        course_id=session.course_id,
        started_at=session.started_at,
        status="active",
    )


@router.put("/{session_id}/end", response_model=AttendanceSessionEndResponse)
async def end_session(
    session_id: UUID,
    current_user: User = Depends(require_role("staff", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return await end_attendance_session(db, current_user, session_id)


@router.get("/active", response_model=AttendanceSessionActiveResponse)
async def active_session(
    room_id: UUID,
    current_user: User = Depends(require_role("staff", "admin")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    return await get_active_attendance_session_for_room(db, current_user, room_id)
