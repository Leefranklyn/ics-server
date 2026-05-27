from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.models.user import User
from ics_backend.services.card import hash_secret, sha256_uid
from ics_backend.config import settings


SESSION_TIMEOUT_SECONDS = 300  # 5 minutes


@dataclass
class RegistrationSession:
    session_id: str
    full_name: str
    email: str
    matric_number: str | None
    role: str
    department: str | None
    level: int | None
    assigned_rooms: list[str]
    created_at: float = field(default_factory=time.time)
    received_uid: str | None = None
    completed: bool = False


# In-memory store for active registration sessions
_active_session: RegistrationSession | None = None


def start_registration_session(
    full_name: str,
    email: str,
    role: str,
    matric_number: str | None = None,
    department: str | None = None,
    level: int | None = None,
    assigned_rooms: list[str] | None = None,
) -> str:
    """Start a new registration session from the web portal. Returns session_id."""
    global _active_session
    session_id = str(uuid.uuid4())
    _active_session = RegistrationSession(
        session_id=session_id,
        full_name=full_name,
        email=email,
        matric_number=matric_number,
        role=role,
        department=department,
        level=level,
        assigned_rooms=assigned_rooms or [],
    )
    return session_id


def get_registration_status() -> dict[str, Any]:
    """Check if a registration session is active (called by ESP32)."""
    global _active_session
    if _active_session is None:
        return {"active": False, "session_id": None}
    # Check timeout
    if time.time() - _active_session.created_at > SESSION_TIMEOUT_SECONDS:
        _active_session = None
        return {"active": False, "session_id": None}
    return {"active": True, "session_id": _active_session.session_id}


def get_pending_session() -> RegistrationSession | None:
    """Get the pending session details (for web portal polling)."""
    global _active_session
    if _active_session is None:
        return None
    if time.time() - _active_session.created_at > SESSION_TIMEOUT_SECONDS:
        _active_session = None
        return None
    return _active_session


def clear_registration_session() -> None:
    """Clear the active registration session."""
    global _active_session
    _active_session = None


async def submit_registration_uid(db: AsyncSession, raw_uid: str) -> dict[str, str]:
    """Called by ESP32 when a card is tapped during active registration.
    
    Stores the UID in the session and marks it as completed.
    Frontend can poll get_pending_session() to see the UID and completion status.
    """
    global _active_session

    if _active_session is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active registration session",
        )

    if time.time() - _active_session.created_at > SESSION_TIMEOUT_SECONDS:
        _active_session = None
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Registration session expired",
        )

    session = _active_session

    # Check if card UID is already registered
    existing_hash = sha256_uid(raw_uid)
    result = await db.execute(
        select(User).where(User.card_uid_sha256 == existing_hash)
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Card is already registered to another user",
        )

    # Check if email already exists
    result = await db.execute(select(User).where(User.email == session.email))
    if result.scalar_one_or_none() is not None:
        _active_session = None
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    default_password = settings.DEFAULT_CARD_PASSWORD or "changeme123"

    user = User(
        full_name=session.full_name,
        email=session.email,
        matric_number=session.matric_number,
        password_hash=hash_secret(default_password),
        role=session.role,
        card_uid_hash=hash_secret(raw_uid),
        card_uid_sha256=sha256_uid(raw_uid),
        card_status="active",
        department=session.department,
        level=session.level,
        assigned_rooms=session.assigned_rooms,
    )
    db.add(user)
    await db.commit()

    # Store UID and mark as completed - keep session active for frontend to display UID
    _active_session.received_uid = raw_uid
    _active_session.completed = True

    return {"status": "ok", "message": "Card registered"}
