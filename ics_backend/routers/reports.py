from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from ics_backend.dependencies import get_current_user, get_db
from ics_backend.models.user import User
from ics_backend.services.attendance import get_attendance_report


router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/attendance", response_model=None)
async def attendance_report(
    room_id: UUID,
    date_from: datetime,
    date_to: datetime,
    student_id: UUID | None = None,
    course_id: UUID | None = None,
    report_format: Literal["json", "csv"] = Query("json", alias="format"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, object]] | StreamingResponse:
    rows = await get_attendance_report(db, current_user, room_id, date_from, date_to, student_id, course_id)
    if report_format == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["timestamp", "full_name", "matric_number", "course_code", "event_type", "door_state"])
        for row in rows:
            writer.writerow(
                [
                    row["timestamp"].isoformat() if isinstance(row["timestamp"], datetime) else row["timestamp"],
                    row["full_name"] or "",
                    row["matric_number"] or "",
                    row["course_code"] or "",
                    row["event_type"],
                    row["door_state"],
                ]
            )
        buffer.seek(0)
        return StreamingResponse(
            iter([buffer.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="attendance.csv"'},
        )
    return rows
