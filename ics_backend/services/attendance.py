from __future__ import annotations

from datetime import datetime, timezone
from statistics import mean
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, cast, func, outerjoin, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import String

from ics_backend.models.access_log import AccessLog
from ics_backend.models.attendance import AttendanceRecord, AttendanceSession
from ics_backend.models.course import Course
from ics_backend.models.environment_log import EnvironmentLog
from ics_backend.models.occupancy_log import OccupancyLog
from ics_backend.models.room import Room
from ics_backend.models.user import User
from ics_backend.schemas.access import AccessEventCreate
from ics_backend.schemas.attendance import AttendanceSessionStartRequest
from ics_backend.schemas.environment import EnvironmentEventCreate
from ics_backend.services.alerts import create_alert
from ics_backend.services.card import find_user_by_uid
from ics_backend.services.schedule import get_active_course


async def process_access_event(db: AsyncSession, payload: AccessEventCreate) -> dict[str, str]:
    room = await _get_room(db, payload.room_id, lock_for_update=True)
    user = await find_user_by_uid(db, payload.card_uid)
    course = await get_active_course(db, payload.room_id, payload.timestamp)
    active_session = await _get_active_attendance_session(db, payload.room_id)
    access_course_id = active_session.course_id if active_session else course.course_id if course else None

    if user is None:
        # Unknown card — log as denied
        access_log = AccessLog(
            user_id=None,
            room_id=payload.room_id,
            course_id=access_course_id,
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
            course_id=access_course_id,
            event_type="denied",
            card_uid=payload.card_uid,
            door_state="closed",
            timestamp=payload.timestamp,
        )
        db.add(access_log)
        await db.commit()
        return {"decision": "denied", "message": "Card suspended"}

    # Determine event type from reader
    access_event_type = "attendance" if active_session else "entry" if payload.reader == "entry" else "exit"

    access_log = AccessLog(
        user_id=user.user_id,
        room_id=payload.room_id,
        course_id=access_course_id,
        event_type=access_event_type,
        card_uid=payload.card_uid,
        door_state="opened",
        timestamp=payload.timestamp,
    )
    db.add(access_log)

    attendance_marked = False
    if active_session:
        result = await db.execute(
            pg_insert(AttendanceRecord)
            .values(
                session_id=active_session.session_id,
                user_id=user.user_id,
                room_id=payload.room_id,
                course_id=active_session.course_id,
                marked_at=payload.timestamp,
                marked_by_card_uid=payload.card_uid,
            )
            .on_conflict_do_nothing(index_elements=["session_id", "user_id"])
        )
        attendance_marked = result.rowcount == 1

    if payload.reader == "entry":
        room.current_occupancy += 1
        if room.current_occupancy > room.capacity:
            await create_alert(
                db,
                room.room_id,
                "overcapacity",
                "critical",
                f"{room.room_name} is over capacity: {room.current_occupancy}/{room.capacity}",
            )
    elif payload.reader == "exit":
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
    if active_session:
        message = "Access Granted - Attendance Marked" if attendance_marked else "Access Granted"
    else:
        message = user.full_name
    return {"decision": "granted", "message": message}


async def start_attendance_session(
    db: AsyncSession,
    current_user: User,
    payload: AttendanceSessionStartRequest,
) -> AttendanceSession:
    await _get_room_for_reader(db, current_user, payload.room_id)

    course_result = await db.execute(select(Course).where(Course.course_id == payload.course_id))
    course = course_result.scalar_one_or_none()
    if course is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Course not found")
    if course.room_id != payload.room_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Course is not assigned to this room")

    active_session = await _get_active_attendance_session(db, payload.room_id)
    if active_session is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An attendance session is already active for this room",
        )

    session = AttendanceSession(
        room_id=payload.room_id,
        course_id=payload.course_id,
        opened_by=current_user.user_id,
        session_name=payload.session_name,
        started_at=datetime.now(timezone.utc),
        status="active",
    )
    db.add(session)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An attendance session is already active for this room",
        ) from exc
    await db.refresh(session)
    return session


async def end_attendance_session(db: AsyncSession, current_user: User, session_id: UUID) -> dict[str, object]:
    session_result = await db.execute(
        select(AttendanceSession).where(AttendanceSession.session_id == session_id).with_for_update()
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attendance session not found")

    await _get_room_for_reader(db, current_user, session.room_id)

    if session.status != "closed":
        session.status = "closed"
        session.ended_at = datetime.now(timezone.utc)

    total_marked = await _count_attendance_records(db, session.session_id)
    await db.commit()
    await db.refresh(session)
    return {
        "session_id": session.session_id,
        "ended_at": session.ended_at,
        "status": session.status,
        "total_marked": total_marked,
    }


async def get_active_attendance_session_for_room(
    db: AsyncSession,
    current_user: User,
    room_id: UUID,
) -> dict[str, object]:
    await _get_room_for_reader(db, current_user, room_id)
    session = await _get_active_attendance_session(db, room_id)
    if session is None:
        return {"session_id": None, "status": "none"}

    marked_count = await _count_attendance_records(db, session.session_id)
    return {
        "session_id": session.session_id,
        "room_id": session.room_id,
        "course_id": session.course_id,
        "started_at": session.started_at,
        "status": session.status,
        "marked_count": marked_count,
    }


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
    session_id: UUID | None = None,
) -> list[dict[str, object]]:
    conditions = [
        AttendanceRecord.room_id == room_id,
        AttendanceRecord.marked_at >= date_from,
        AttendanceRecord.marked_at <= date_to,
    ]
    if student_id is not None:
        conditions.append(AttendanceRecord.user_id == student_id)
    if course_id is not None:
        conditions.append(AttendanceRecord.course_id == course_id)
    if session_id is not None:
        conditions.append(AttendanceRecord.session_id == session_id)

    if current_user.role == "staff":
        assigned_rooms = [str(item) for item in (current_user.assigned_rooms or [])]
        if str(room_id) not in assigned_rooms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Room is not assigned to this staff user")
        conditions.append(cast(AttendanceRecord.room_id, String).in_(assigned_rooms))
    elif current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    query = (
        select(
            AttendanceRecord.marked_at,
            AttendanceRecord.session_id,
            User.full_name,
            User.matric_number,
            Course.course_code,
            Course.course_name,
            AttendanceSession.session_name,
            AttendanceSession.started_at,
        )
        .select_from(AttendanceRecord)
        .join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.session_id)
        .outerjoin(User, AttendanceRecord.user_id == User.user_id)
        .outerjoin(Course, AttendanceRecord.course_id == Course.course_id)
        .where(and_(*conditions))
        .order_by(AttendanceRecord.marked_at.asc())
    )
    result = await db.execute(query)
    return [
        {
            "timestamp": row.marked_at,
            "full_name": row.full_name,
            "matric_number": row.matric_number,
            "course_code": row.course_code,
            "course_name": row.course_name,
            "session_id": row.session_id,
            "session_name": row.session_name,
            "session_started_at": row.started_at,
            "event_type": "attendance",
            "marked_at": row.marked_at,
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


async def _get_active_attendance_session(db: AsyncSession, room_id: UUID) -> AttendanceSession | None:
    result = await db.execute(
        select(AttendanceSession)
        .where(and_(AttendanceSession.room_id == room_id, AttendanceSession.status == "active"))
        .order_by(AttendanceSession.started_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _count_attendance_records(db: AsyncSession, session_id: UUID) -> int:
    result = await db.execute(
        select(func.count()).select_from(AttendanceRecord).where(AttendanceRecord.session_id == session_id)
    )
    return int(result.scalar_one())


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
