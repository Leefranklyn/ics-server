from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import String

from ics_backend.models.course import Course
from ics_backend.models.room import Room
from ics_backend.models.user import User


async def list_courses_for_room(db: AsyncSession, current_user: User, room_id: UUID) -> list[Course]:
    conditions = [Room.room_id == room_id]
    if current_user.role == "staff":
        assigned_rooms = [str(item) for item in (current_user.assigned_rooms or [])]
        if str(room_id) not in assigned_rooms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Room is not assigned to this staff user")
        conditions.append(cast(Room.room_id, String).in_(assigned_rooms))
    elif current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    room = await db.scalar(select(Room).where(and_(*conditions)))
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    result = await db.execute(select(Course).where(Course.room_id == room_id).order_by(Course.course_code.asc()))
    return list(result.scalars().all())
