from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_db, verify_api_key
from ics_backend.schemas.access import AccessEventCreate, AccessEventResponse, EspUserCompact
from ics_backend.schemas.environment import EnvironmentEventCreate, EnvironmentEventResponse
from ics_backend.schemas.room import RoomConfigResponse
from ics_backend.services.attendance import get_room_config, process_access_event, process_environment_event
from ics_backend.services.card import active_esp_users


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["esp32"], dependencies=[Depends(verify_api_key)])


@router.post("/access", response_model=AccessEventResponse)
async def access_event(payload: AccessEventCreate, db: AsyncSession = Depends(get_db)) -> AccessEventResponse:
    access_log = await process_access_event(db, payload)
    logger.info(
        "esp32 access room_id=%s event_type=%s timestamp=%s user_found=%s",
        payload.room_id,
        payload.event_type,
        payload.timestamp.isoformat(),
        access_log.user_id is not None,
    )
    return AccessEventResponse(log_id=access_log.log_id)


@router.post("/environment", response_model=EnvironmentEventResponse)
async def environment_event(
    payload: EnvironmentEventCreate, db: AsyncSession = Depends(get_db)
) -> EnvironmentEventResponse:
    await process_environment_event(db, payload)
    logger.info(
        "esp32 environment room_id=%s event_type=environment timestamp=%s user_found=%s",
        payload.room_id,
        payload.timestamp.isoformat(),
        False,
    )
    return EnvironmentEventResponse()


@router.get("/rooms/{room_id}/config", response_model=RoomConfigResponse)
async def room_config(room_id: UUID, db: AsyncSession = Depends(get_db)) -> RoomConfigResponse:
    room = await get_room_config(db, room_id)
    logger.info("esp32 config room_id=%s event_type=config timestamp=server user_found=%s", room_id, False)
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
    logger.info("esp32 users room_id=none event_type=user_sync timestamp=server user_found=%s", False)
    return await active_esp_users(db)
