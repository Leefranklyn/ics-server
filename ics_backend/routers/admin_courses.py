from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_db, require_role
from ics_backend.models.user import User
from ics_backend.schemas.course import CourseResponse
from ics_backend.services.course import list_courses_for_room


router = APIRouter(prefix="/api/admin", tags=["admin courses"])


@router.get("/rooms/{room_id}/courses", response_model=list[CourseResponse])
async def room_courses(
    room_id: UUID,
    current_user: User = Depends(require_role("staff", "admin")),
    db: AsyncSession = Depends(get_db),
) -> list[CourseResponse]:
    return await list_courses_for_room(db, current_user, room_id)
