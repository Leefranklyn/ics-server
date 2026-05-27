from __future__ import annotations

from datetime import datetime
from statistics import mean
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, cast, outerjoin, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import String

from ics_backend.models.access_log import AccessLog
from ics_backend.models.course import Course
from ics_backend.models.environment_log import EnvironmentLog
from ics_backend.models.occupancy_log import OccupancyLog
from ics_backend.models.room import Room
from ics_backend.models.user import User
from ics_backend.schemas.access import AccessEventCreate
from ics_backend.schemas.environment import EnvironmentEventCreate
from ics_backend.services.alerts import create_alert
from ics_backend.services.card import find_user_by_uid
from ics_backend.services.schedule import get_active_course


async def process_access_event(db: AsyncSession, payload: AccessEventCreate) -> dict[str, str]:
    room = await _get_room(db, payload.room_id, lock_for_update=True)
    user = await find_user_by_uid(db, payload.card_uid)
    course = await get_active_course(db, payload.room_id, payload.timestamp)

    if user is None:
        # Unknown card — log as denied
        access_log = AccessLog(
            user_id=None,
            room_id=payload.room_id,
            course_id=course.course_id if course else None,
            event_type="denied",
            card_uid=payload.card_uid,
            door_state="closed",
            timestamp=payload.timestamp,
        )
        db.add(access_log)
        await db.commit()
        return {"decision": "denied", "message": "Unknown card"}

    if user.card_status != "active":
        access_log = AccessLog(
            user_id=user.user_id,
            room_id=payload.room_id,
            course_id=course.course_id if course else None,
            event_type="denied",
            card_uid=payload.card_uid,
            door_state="closed",
            timestamp=payload.timestamp,
        )
        db.add(access_log)
        await db.commit()
        return {"decision": "denied", "message": "Card suspended"}

    # Determine event type from reader
    event_type = "entry" if payload.reader == "entry" else "exit"

    access_log = AccessLog(
        user_id=user.user_id,
        room_id=payload.room_id,
        course_id=course.course_id if course else None,
        event_type=event_type,
        card_uid=payload.card_uid,
        door_state="opened",
        timestamp=payload.timestamp,
    )
    db.add(access_log)

    if event_type == "entry":
        room.current_occupancy += 1
        if room.current_occupancy > room.capacity:
            await create_alert(
                db,
                room.room_id,
                "overcapacity",
                "critical",
                f"{room.room_name} is over capacity: {room.current_occupancy}/{room.capacity}",
            )
    elif event_type == "exit":
        room.current_occupancy = max(room.current_occupancy - 1, 0)

    db.add(
        OccupancyLog(
            room_id=room.room_id,
            occupancy_count=room.current_occupancy,
            ac_setpoint=room.ac_setpoint,
            timestamp=payload.timestamp,
        )
    )
    await db.commit()
    await db.refresh(access_log)
    return {"decision": "granted", "message": user.full_name}


async def process_environment_event(db: AsyncSession, payload: EnvironmentEventCreate) -> None:
    room = await _get_room(db, payload.room_id)
    db.add(
        EnvironmentLog(
            room_id=payload.room_id,
            temperature=payload.temperature,
            humidity=payload.humidity,
            light_level=payload.light_level,
            ac_setpoint=payload.ac_setpoint,
            timestamp=payload.timestamp,
        )
    )
    if payload.temperature > 35:
        await create_alert(
            db,
            payload.room_id,
            "high_temp",
            "warning",
            f"{room.room_name} temperature is high at {payload.temperature:.1f}C",
        )
    await db.commit()


async def get_room_config(db: AsyncSession, room_id: UUID) -> Room:
    return await _get_room(db, room_id)


async def get_dashboard_room(db: AsyncSession, current_user: User, room_id: UUID) -> dict[str, object]:
    room = await _get_room_for_reader(db, current_user, room_id)
    latest_env_conditions = _room_data_conditions(EnvironmentLog.room_id, current_user, room_id)
    latest_env_result = await db.execute(
        select(EnvironmentLog)
        .where(and_(*latest_env_conditions))
        .order_by(EnvironmentLog.timestamp.desc())
        .limit(1)
    )
    latest_env = latest_env_result.scalar_one_or_none()

    recent_result = await db.execute(
        select(
            User.full_name,
            User.matric_number,
            AccessLog.event_type,
            AccessLog.timestamp,
            AccessLog.door_state,
        )
        .select_from(outerjoin(AccessLog, User, AccessLog.user_id == User.user_id))
        .where(and_(*_room_data_conditions(AccessLog.room_id, current_user, room_id)))
        .order_by(AccessLog.timestamp.desc())
        .limit(20)
    )
    recent_events = [
        {
            "full_name": row.full_name,
            "matric_number": row.matric_number,
            "event_type": row.event_type,
            "timestamp": row.timestamp,
            "door_state": row.door_state,
        }
        for row in recent_result
    ]
    return {
        "room_id": room.room_id,
        "room_name": room.room_name,
        "current_occupancy": room.current_occupancy,
        "capacity": room.capacity,
        "lock_state": room.lock_state,
        "ac_setpoint": room.ac_setpoint,
        "temperature": latest_env.temperature if latest_env else None,
        "humidity": latest_env.humidity if latest_env else None,
        "recent_events": recent_events,
    }


async def get_attendance_report(
    db: AsyncSession,
    current_user: User,
    room_id: UUID,
    date_from: datetime,
    date_to: datetime,
    student_id: UUID | None = None,
    course_id: UUID | None = None,
) -> list[dict[str, object]]:
    conditions = [
        AccessLog.room_id == room_id,
        AccessLog.timestamp >= date_from,
        AccessLog.timestamp <= date_to,
    ]
    if student_id is not None:
        conditions.append(AccessLog.user_id == student_id)
    if course_id is not None:
        conditions.append(AccessLog.course_id == course_id)

    if current_user.role == "student":
        if student_id is not None and student_id != current_user.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Students can only read their own logs")
        conditions.append(AccessLog.user_id == current_user.user_id)
    elif current_user.role == "staff":
        assigned_rooms = [str(item) for item in (current_user.assigned_rooms or [])]
        if str(room_id) not in assigned_rooms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Room is not assigned to this staff user")
        conditions.append(cast(AccessLog.room_id, String).in_(assigned_rooms))
    elif current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    query = (
        select(
            AccessLog.timestamp,
            User.full_name,
            User.matric_number,
            Course.course_code,
            Course.course_name,
            AccessLog.event_type,
            AccessLog.door_state,
        )
        .select_from(AccessLog)
        .outerjoin(User, AccessLog.user_id == User.user_id)
        .outerjoin(Course, AccessLog.course_id == Course.course_id)
        .where(and_(*conditions))
        .order_by(AccessLog.timestamp.asc())
    )
    result = await db.execute(query)
    return [
        {
            "timestamp": row.timestamp,
            "full_name": row.full_name,
            "matric_number": row.matric_number,
            "course_code": row.course_code,
            "course_name": row.course_name,
            "event_type": row.event_type,
            "door_state": row.door_state,
        }
        for row in result
    ]


async def get_energy_analytics(
    db: AsyncSession,
    current_user: User,
    room_id: UUID,
    date_from: datetime,
    date_to: datetime,
) -> dict[str, object]:
    await _get_room_for_reader(db, current_user, room_id)
    conditions = _room_data_conditions(EnvironmentLog.room_id, current_user, room_id)
    conditions.extend([EnvironmentLog.timestamp >= date_from, EnvironmentLog.timestamp <= date_to])
    result = await db.execute(select(EnvironmentLog).where(and_(*conditions)))
    logs = list(result.scalars().all())
    active_intervals = {
        log.timestamp.replace(minute=(log.timestamp.minute // 5) * 5, second=0, microsecond=0)
        for log in logs
        if log.ac_setpoint < 28
    }
    runtime_hours = round(len(active_intervals) * 5 / 60, 2)
    temperatures = [log.temperature for log in logs]
    humidities = [log.humidity for log in logs]
    return {
        "room_id": room_id,
        "date_from": date_from,
        "date_to": date_to,
        "runtime_hours": runtime_hours,
        "estimated_kwh": round(runtime_hours * 1.5, 2),
        "avg_temperature": round(mean(temperatures), 2) if temperatures else None,
        "avg_humidity": round(mean(humidities), 2) if humidities else None,
    }


async def update_room_windows(db: AsyncSession, room_id: UUID, time_windows: dict[str, object]) -> None:
    result = await db.execute(
        update(Room).where(Room.room_id == room_id).values(time_windows=time_windows).returning(Room.room_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    await db.commit()


async def _get_room(db: AsyncSession, room_id: UUID, lock_for_update: bool = False) -> Room:
    query: Select[tuple[Room]] = select(Room).where(Room.room_id == room_id)
    if lock_for_update:
        query = query.with_for_update()
    result = await db.execute(query)
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


async def _get_room_for_reader(db: AsyncSession, current_user: User, room_id: UUID) -> Room:
    if current_user.role == "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Students cannot access this room data")
    conditions = [Room.room_id == room_id]
    if current_user.role == "staff":
        assigned_rooms = [str(item) for item in (current_user.assigned_rooms or [])]
        if str(room_id) not in assigned_rooms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Room is not assigned to this staff user")
        conditions.append(cast(Room.room_id, String).in_(assigned_rooms))
    elif current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    result = await db.execute(select(Room).where(and_(*conditions)))
    room = result.scalar_one_or_none()
    if room is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


def _room_data_conditions(room_column, current_user: User, room_id: UUID) -> list[object]:
    conditions: list[object] = [room_column == room_id]
    if current_user.role == "staff":
        assigned_rooms = [str(item) for item in (current_user.assigned_rooms or [])]
        conditions.append(cast(room_column, String).in_(assigned_rooms))
    return conditions
