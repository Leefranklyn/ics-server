from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Select, and_, cast, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.sqltypes import String

from ics_backend.models.alerts import Alert
from ics_backend.models.user import User


async def create_alert(
    db: AsyncSession,
    room_id: UUID,
    alert_type: str,
    severity: str,
    message: str,
) -> Alert:
    existing_result = await db.execute(
        select(Alert).where(
            Alert.room_id == room_id,
            Alert.alert_type == alert_type,
            Alert.acknowledged.is_(False),
        )
    )
    existing = existing_result.scalar_one_or_none()
    if existing is not None:
        return existing

    alert = Alert(room_id=room_id, alert_type=alert_type, severity=severity, message=message)
    db.add(alert)
    await db.flush()
    return alert


async def list_alerts(
    db: AsyncSession,
    current_user: User,
    acknowledged: bool | None = None,
    room_id: UUID | None = None,
) -> list[Alert]:
    if current_user.role == "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Students cannot view alerts")

    query: Select[tuple[Alert]] = select(Alert)
    conditions = []
    if acknowledged is not None:
        conditions.append(Alert.acknowledged.is_(acknowledged))
    if room_id is not None:
        conditions.append(Alert.room_id == room_id)
    if current_user.role == "staff":
        assigned_rooms = [str(item) for item in (current_user.assigned_rooms or [])]
        if room_id is not None and str(room_id) not in assigned_rooms:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Room is not assigned to this staff user")
        conditions.append(cast(Alert.room_id, String).in_(assigned_rooms))
    if conditions:
        query = query.where(and_(*conditions))
    query = query.order_by(Alert.triggered_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def acknowledge_alert(db: AsyncSession, current_user: User, alert_id: UUID) -> Alert:
    if current_user.role == "student":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Students cannot acknowledge alerts")

    conditions = [Alert.alert_id == alert_id]
    if current_user.role == "staff":
        assigned_rooms = [str(item) for item in (current_user.assigned_rooms or [])]
        conditions.append(cast(Alert.room_id, String).in_(assigned_rooms))

    result = await db.execute(
        update(Alert).where(and_(*conditions)).values(acknowledged=True).returning(Alert.alert_id)
    )
    updated_alert_id = result.scalar_one_or_none()
    if updated_alert_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    await db.commit()
    alert_result = await db.execute(select(Alert).where(Alert.alert_id == updated_alert_id))
    alert = alert_result.scalar_one()
    return alert
