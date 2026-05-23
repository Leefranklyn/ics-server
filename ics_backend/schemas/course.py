from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class CourseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: UUID
    course_code: str
    course_name: str
    room_id: UUID
    lecturer_id: UUID
    schedule: dict[str, Any] | None
    semester: str | None
    academic_year: str | None
