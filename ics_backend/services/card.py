from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.config import settings
from ics_backend.models.course import Course
from ics_backend.models.enrollment import Enrollment
from ics_backend.models.user import User
from ics_backend.schemas.user import AdminCardCreate


pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")


def hash_secret(value: str) -> str:
    return pwd_context.hash(value)


def sha256_uid(raw_uid: str) -> str:
    """Compute SHA-256 hex digest of a raw card UID — matches ESP32 mbedtls implementation."""
    return hashlib.sha256(raw_uid.encode()).hexdigest()


def verify_secret(plain_value: str, hashed_value: str) -> bool:
    return pwd_context.verify(plain_value, hashed_value)


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.user_id),
        "role": user.role,
        "rooms": user.assigned_rooms or [],
        "iat": int(now.timestamp()),
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_secret(password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    return user


async def find_user_by_uid(db: AsyncSession, raw_uid: str) -> User | None:
    hashed = sha256_uid(raw_uid)
    result = await db.execute(
        select(User).where(User.card_status == "active", User.card_uid_sha256 == hashed)
    )
    return result.scalar_one_or_none()


async def create_card_user(db: AsyncSession, payload: AdminCardCreate) -> UUID:
    if not settings.DEFAULT_CARD_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="DEFAULT_CARD_PASSWORD is not configured",
        )

    assigned_rooms = [str(room_id) for room_id in payload.assigned_rooms]
    user = User(
        full_name=payload.full_name,
        email=payload.email,
        matric_number=payload.matric_number,
        password_hash=hash_secret(settings.DEFAULT_CARD_PASSWORD),
        role=payload.role,
        card_uid_hash=hash_secret(payload.raw_card_uid),
        card_uid_sha256=sha256_uid(payload.raw_card_uid),
        card_status="active",
        department=payload.department,
        level=payload.level,
        assigned_rooms=assigned_rooms,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.user_id


async def update_card_status(db: AsyncSession, user_id: UUID, status_value: str) -> None:
    result = await db.execute(
        update(User).where(User.user_id == user_id).values(card_status=status_value).returning(User.user_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    await db.commit()


async def list_users(db: AsyncSession, page: int, limit: int) -> tuple[int, list[User]]:
    page = max(page, 1)
    limit = min(max(limit, 1), 100)
    total_result = await db.execute(select(func.count()).select_from(User))
    total = int(total_result.scalar_one())
    users_result = await db.execute(
        select(User).order_by(User.created_at.desc()).offset((page - 1) * limit).limit(limit)
    )
    return total, list(users_result.scalars().all())


async def active_esp_users(db: AsyncSession) -> list[dict[str, object]]:
    result = await db.execute(
        select(User).where(User.card_status == "active", User.card_uid_sha256.is_not(None)).order_by(User.full_name)
    )
    users = list(result.scalars().all())
    rows: list[dict[str, object]] = []
    for user in users:
        rows.append(
            {
                "uid_fast": user.card_uid_sha256,
                "user_id": user.user_id,
                "role": user.role,
                "name": user.full_name,
            }
        )
    return rows


async def _student_enrolled_rooms(db: AsyncSession, user_id: UUID) -> list[str]:
    query: Select[tuple[UUID]] = (
        select(Course.room_id)
        .join(Enrollment, Enrollment.course_id == Course.course_id)
        .where(Enrollment.student_id == user_id, Enrollment.status == "active")
        .distinct()
    )
    result = await db.execute(query)
    return [str(room_id) for room_id in result.scalars().all()]
