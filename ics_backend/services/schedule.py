from __future__ import annotations

from datetime import datetime, time, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.models.course import Course


DAY_ALIASES = {
    "monday": "monday",
    "mon": "monday",
    "tuesday": "tuesday",
    "tue": "tuesday",
    "wednesday": "wednesday",
    "wed": "wednesday",
    "thursday": "thursday",
    "thu": "thursday",
    "friday": "friday",
    "fri": "friday",
    "saturday": "saturday",
    "sat": "saturday",
    "sunday": "sunday",
    "sun": "sunday",
}


async def get_active_course(db: AsyncSession, room_id: UUID, timestamp: datetime) -> Course | None:
    result = await db.execute(select(Course).where(Course.room_id == room_id, Course.schedule.is_not(None)))
    target_day = timestamp.strftime("%A").lower()
    for course in result.scalars():
        schedule = course.schedule or {}
        schedule_day = DAY_ALIASES.get(str(schedule.get("day", "")).strip().lower())
        if schedule_day != target_day:
            continue
        start_time = _parse_time(schedule.get("start_time"))
        duration_mins = int(schedule.get("duration_mins") or 0)
        if start_time is None or duration_mins <= 0:
            continue
        starts_at = datetime.combine(timestamp.date(), start_time, tzinfo=timestamp.tzinfo)
        ends_at = starts_at + timedelta(minutes=duration_mins)
        if starts_at <= timestamp < ends_at:
            return course
    return None


def _parse_time(value: object) -> time | None:
    if not isinstance(value, str):
        return None
    try:
        return time.fromisoformat(value)
    except ValueError:
        return None
