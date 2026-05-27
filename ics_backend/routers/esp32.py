from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_db, verify_api_key
from ics_backend.schemas.access import (
    AccessEventCreate,
    AccessEventResponse,
    EspUserCompact,
    RegistrationStatusResponse,
    RegistrationUidCreate,
    RegistrationUidResponse,
)
from ics_backend.schemas.environment import EnvironmentEventCreate, EnvironmentEventResponse
from ics_backend.schemas.room import RoomConfigResponse
from ics_backend.services.attendance import get_room_config, process_access_event, process_environment_event
from ics_backend.services.card import active_esp_users
from ics_backend.services.registration import get_registration_status, submit_registration_uid


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["esp32"], dependencies=[Depends(verify_api_key)])


@router.post("/access", response_model=AccessEventResponse)
async def access_event(payload: AccessEventCreate, db: AsyncSession = Depends(get_db)) -> AccessEventResponse:
    result = await process_access_event(db, payload)
    logger.info(
        "esp32 access room_id=%s reader=%s timestamp=%s decision=%s",
        payload.room_id,
        payload.reader,
        payload.timestamp.isoformat(),
        result["decision"],
    )
    return AccessEventResponse(decision=result["decision"], message=result["message"])


@router.post("/environment", response_model=EnvironmentEventResponse)
async def environment_event(
    payload: EnvironmentEventCreate, db: AsyncSession = Depends(get_db)
) -> EnvironmentEventResponse:
    await process_environment_event(db, payload)
    logger.info(
        "esp32 environment room_id=%s timestamp=%s",
        payload.room_id,
        payload.timestamp.isoformat(),
    )
    return EnvironmentEventResponse()


@router.get("/rooms/{room_id}/config", response_model=RoomConfigResponse)
async def room_config(room_id: UUID, db: AsyncSession = Depends(get_db)) -> RoomConfigResponse:
    room = await get_room_config(db, room_id)
    logger.info("esp32 config room_id=%s", room_id)
    return RoomConfigResponse(
        room_id=room.room_id,
        capacity=room.capacity,
        time_windows=room.time_windows,
        ac_setpoint=room.ac_setpoint,
        lock_state=room.lock_state,
        current_occupancy=room.current_occupancy,
    )


@router.get("/users", response_model=list[EspUserCompact])
async def users_for_esp32(db: AsyncSession = Depends(get_db)) -> list[dict[str, object]]:
    logger.info("esp32 user_sync requested")
    return await active_esp_users(db)


@router.get("/registration/status", response_model=RegistrationStatusResponse)
async def registration_status() -> RegistrationStatusResponse:
    status = get_registration_status()
    logger.info("esp32 registration_status active=%s", status["active"])
    return RegistrationStatusResponse(**status)


@router.post("/registration/uid", response_model=RegistrationUidResponse)
async def registration_uid(
    payload: RegistrationUidCreate, db: AsyncSession = Depends(get_db)
) -> RegistrationUidResponse:
    result = await submit_registration_uid(db, payload.uid)
    logger.info("esp32 registration_uid result=%s", result["status"])
    return RegistrationUidResponse(**result)
