# Frontend Attendance System Updates

The backend now uses a session-based attendance model. Card taps only count as attendance when a lecturer/staff member has opened an active attendance session for a room.

## Main Behavior Change

- Attendance is no longer inferred from normal entry/exit access logs.
- A staff/admin user must start an attendance session before students tap cards.
- During an active session, the first valid card tap by a user creates one attendance record.
- Repeated taps by the same user during the same session still grant access but do not create duplicate attendance.
- When no session is active, card taps behave as normal entry/exit access only and do not affect attendance reports.

## Auth

All attendance session endpoints require a staff or admin bearer token.

Use:

```http
Authorization: Bearer <token>
```

## Start Attendance Session

```http
POST /api/admin/attendance/session/start
```

Request:

```json
{
  "room_id": "uuid-string",
  "course_id": "uuid-string",
  "session_name": "CS101 - Monday Lecture Week 5"
}
```

`session_name` is optional.

Response:

```json
{
  "session_id": "uuid-string",
  "room_id": "uuid-string",
  "course_id": "uuid-string",
  "started_at": "2026-05-31T14:00:00Z",
  "status": "active"
}
```

Notes:

- Only one active attendance session is allowed per room.
- If a session is already active for the room, the backend returns `409`.
- The selected course must belong to the selected room.

## Get Courses For Room

```http
GET /api/admin/rooms/{room_id}/courses
```

Response:

```json
[
  {
    "course_id": "uuid-string",
    "course_code": "CSC 214",
    "course_name": "Data Structures",
    "room_id": "room-uuid",
    "lecturer_id": "lecturer-uuid",
    "schedule": {
      "day": "Monday",
      "start_time": "09:00",
      "duration_mins": 90
    },
    "semester": "Rain",
    "academic_year": "2025/2026"
  }
]
```

Frontend use:

- Fetch this after a room is selected.
- Pass the returned array into `SessionManager` as `courses`.
- Staff users can only fetch courses for rooms assigned to them.

## Get Active Session For Room

```http
GET /api/admin/attendance/session/active?room_id=<room_id>
```

Response when active:

```json
{
  "session_id": "uuid-string",
  "room_id": "uuid-string",
  "course_id": "uuid-string",
  "started_at": "2026-05-31T14:00:00Z",
  "status": "active",
  "marked_count": 15
}
```

Response when none active:

```json
{
  "session_id": null,
  "status": "none"
}
```

Frontend use:

- Poll or fetch this when opening the dashboard/attendance page.
- Show active/closed state clearly.
- Use `marked_count` as the live attendance count for the active session.

## End Attendance Session

```http
PUT /api/admin/attendance/session/{session_id}/end
```

Response:

```json
{
  "session_id": "uuid-string",
  "ended_at": "2026-05-31T15:00:00Z",
  "status": "closed",
  "total_marked": 42
}
```

Frontend use:

- After ending a session, refresh the active session query for the room.
- Display `total_marked` in the confirmation/result state.

## Attendance Report

```http
GET /api/reports/attendance
```

Query parameters:

| Parameter | Required | Notes |
|---|---:|---|
| `room_id` | Yes | Room UUID |
| `date_from` | Yes | ISO datetime |
| `date_to` | Yes | ISO datetime |
| `course_id` | No | Filter by course |
| `session_id` | No | Filter by one attendance session |
| `student_id` | No | Filter by student/user |
| `format` | No | `json` or `csv`, defaults to `json` |

Example:

```http
GET /api/reports/attendance?room_id=<room_id>&date_from=2026-05-31T00:00:00Z&date_to=2026-05-31T23:59:59Z
```

JSON response:

```json
[
  {
    "timestamp": "2026-05-31T14:05:00Z",
    "full_name": "John Doe",
    "matric_number": "ST/001/2024",
    "course_code": "CS101",
    "course_name": "Introduction to Computer Science",
    "session_id": "uuid-string",
    "session_name": "CS101 - Monday Lecture Week 5",
    "session_started_at": "2026-05-31T14:00:00Z",
    "event_type": "attendance",
    "marked_at": "2026-05-31T14:05:00Z"
  }
]
```

CSV export now includes:

```text
timestamp,full_name,matric_number,course_code,session_id,session_name,session_started_at,event_type,marked_at
```

Important report changes:

- Reports now return only records from attendance sessions.
- Entry/exit access logs are not included.
- `event_type` is always `"attendance"`.
- `door_state` has been removed from attendance report rows.

## ESP/Card Tap Response Messages

When a student taps during an active attendance session:

```json
{
  "decision": "granted",
  "message": "Access Granted - Attendance Marked"
}
```

When the same user taps again during the same session:

```json
{
  "decision": "granted",
  "message": "Access Granted"
}
```

When no session is active, the existing normal access behavior remains.

## Suggested Frontend Flow

1. User selects a room and course.
2. Frontend calls `GET /api/admin/attendance/session/active?room_id=<room_id>`.
3. If no session is active, show a start attendance action.
4. On start, call `POST /api/admin/attendance/session/start`.
5. While active, show session name, start time, course, and marked count.
6. Refresh active session data periodically or after known card activity.
7. On end, call `PUT /api/admin/attendance/session/{session_id}/end`.
8. Attendance tables should use `/api/reports/attendance`, not access log data.

## Error States To Handle

- `401`: Missing or invalid token.
- `403`: User is not staff/admin or is not assigned to the room.
- `404`: Room, course, or session not found.
- `409`: Another active attendance session already exists for the room.
- `422`: Invalid UUID, datetime, or request body.
