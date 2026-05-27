# Intelligent Classroom Saver - Backend API Documentation

A comprehensive smart classroom management system API built with FastAPI, designed to manage room access control, occupancy tracking, environment monitoring, and attendance reporting.

## Table of Contents

- [Overview](#overview)
- [Authentication](#authentication)
- [Base URL](#base-url)
- [ESP32 Device Endpoints](#esp32-device-endpoints)
- [Frontend/User Endpoints](#frontenduser-endpoints)
- [Error Handling](#error-handling)
- [Status Codes](#status-codes)

---

## Overview

This API powers a smart classroom system with the following core features:

- **Access Control**: Card-based access with entry/exit tracking
- **Occupancy Monitoring**: Real-time room occupancy tracking
- **Environment Monitoring**: Temperature, humidity, and light level monitoring
- **User Management**: Student, staff, and admin user roles
- **Card Registration**: Dynamic card registration sessions
- **Analytics**: Energy consumption and attendance analytics
- **Alerts**: Room condition monitoring with alert system
- **Reporting**: Attendance report generation in JSON and CSV formats

---

## Authentication

The API uses two authentication mechanisms:

### 1. Bearer Token Authentication (Frontend/Users)
Used by frontend applications and user dashboards.

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Token Acquisition:**
- Call `/api/auth/login` with email and password
- Receive JWT token in response
- Include token in `Authorization` header for all subsequent requests

**Token Details:**
- Algorithm: HS256 (configurable via JWT_ALGORITHM)
- Default expiration: 30 minutes (configurable via ACCESS_TOKEN_EXPIRE_MINUTES)
- Subject: User UUID

### 2. API Key Authentication (ESP32 Devices)
Used by ESP32 IoT devices for sensor data and access events.

**Headers:**
```
X-API-Key: <ESP32_API_KEY>
```

**Security:**
- Set via `ESP32_API_KEY` environment variable
- All ESP32 endpoints require this header
- Invalid keys return 403 Forbidden

---

## Base URL

```
https://intelligent-classroom-saver-api.onrender.com
```

Production URLs will vary based on deployment.

---

## ESP32 Device Endpoints

All ESP32 endpoints require `X-API-Key` header and are located under `/api` prefix.

### Card Access & Registration Workflow

The ESP32 device follows this workflow when a card is tapped:

#### **Flow for Known Users (in local memory):**
1. ESP32 reads card UID from reader
2. ESP32 checks its **local memory** (populated by periodic sync from `/api/users`)
3. If user found in local memory:
   - **ALLOW**: Unlock door immediately
   - If entry reader: Mark attendance in server via `/api/access` → returns "granted"
   - If exit reader: Only unlock door via `/api/access` → returns "granted"

#### **Flow for Unknown Users (not in local memory):**
1. ESP32 reads card UID from reader
2. ESP32 checks local memory - not found
3. ESP32 sends card UID to server via `/api/access`
4. Server responds with:
   - "denied" → Unknown card, check for active registration
5. ESP32 checks if registration is active via `/api/registration/status`
6. If registration **IS ACTIVE**:
   - ESP32 sends the UID to `/api/registration/uid`
   - Server creates new user with provided card UID
   - Server stores UID in registration session
   - **Frontend polls** `/api/admin/registration/status` and receives the UID
   - Frontend displays: "✓ Card UID: 04D15401521ABC - User created!"
   - Card is now registered and future taps will succeed
   - Display UI confirmation on ESP32
7. If registration **NOT ACTIVE**:
   - Log as unknown card access attempt
   - Deny access (keep door locked)
   - Display UI message on ESP32

#### **Card Status Checks:**
- Card must have `card_status = "active"` in database
- Suspended cards are denied access (response: "Card suspended")
- Suspended cards can be reactivated by admin via `/api/admin/cards/{user_id}/status`

#### **Periodic Synchronization:**
- ESP32 should periodically call `/api/users` (recommended: every 30 minutes)
- This populates ESP32 local memory with all active users
- Allows fast, offline access control decisions
- Reduces server load from every tap triggering a lookup

#### **Time-Based Access Control:**
- ESP32 should check room `time_windows` from `/api/rooms/{room_id}/config`
- Access can be allowed/denied based on current time and day
- Room capacity limits trigger `"occupancy_critical"` alerts

---

### Health Check (Public)

```
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2026-05-27T10:30:00+00:00"
}
```

---

### 1. Submit Access Event

**Endpoint:** `POST /api/access`

**Authentication:** X-API-Key (ESP32)

**Purpose:** Log a card access event and validate user access. The server records the access attempt and returns the decision (granted/denied). 

**Important:** This endpoint is called AFTER the ESP32 firmware has made the door unlock/lock decision based on local memory. The server response is primarily for logging and determining next steps (e.g., if denied, check for active registration).

**Request Body:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "card_uid": "04D15401521ABC",
  "reader": "entry",
  "timestamp": "2026-05-27T10:30:00+00:00"
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| room_id | UUID | Yes | The room where access is being attempted |
| card_uid | string | Yes | The UID of the card being read (1-50 chars) |
| reader | string | Yes | Either "entry" or "exit" |
| timestamp | ISO 8601 datetime | Yes | When the card was read |

**Response:**
```json
{
  "decision": "granted",
  "message": "Access granted for John Doe"
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| decision | string | "granted" or "denied" |
| message | string | Human-readable explanation (user name on grant, reason on deny) |

**Possible Responses:**
- **granted**: User exists and card is active. Attendance is marked (entry reader) or just recorded (exit reader). Door unlock signal sent to ESP32.
- **denied "Unknown card"**: Card UID not found in system. ESP32 should check `/api/registration/status` to see if registration is active.
- **denied "Card suspended"**: User exists but card has been suspended by admin. Access is denied.

**Status Codes:**
- 200 OK - Event processed successfully
- 401 Unauthorized - Missing or invalid X-API-Key
- 422 Unprocessable Entity - Invalid request format

**Example (CURL):**
```bash
curl -X POST https://intelligent-classroom-saver-api.onrender.com/api/access \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_esp32_api_key" \
  -d '{
    "room_id": "550e8400-e29b-41d4-a716-446655440000",
    "card_uid": "04D15401521ABC",
    "reader": "entry",
    "timestamp": "2026-05-27T10:30:00Z"
  }'
```

---

### 2. Submit Environment Event

**Endpoint:** `POST /api/environment`

**Authentication:** X-API-Key (ESP32)

**Purpose:** Log environmental sensor readings from the room (temperature, humidity, light level).

**Request Body:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "temperature": 22.5,
  "humidity": 45.3,
  "light_level": 350,
  "ac_setpoint": 24,
  "timestamp": "2026-05-27T10:30:00+00:00"
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| room_id | UUID | Yes | The room providing sensor data |
| temperature | float | Yes | Room temperature in Celsius |
| humidity | float | Yes | Room humidity as percentage (0-100) |
| light_level | integer | Yes | Light level in lux |
| ac_setpoint | integer | Yes | AC/heating target temperature in Celsius |
| timestamp | ISO 8601 datetime | Yes | When the reading was taken |

**Response:**
```json
{
  "status": "ok"
}
```

**Status Codes:**
- 200 OK - Event logged successfully
- 401 Unauthorized - Missing or invalid X-API-Key
- 422 Unprocessable Entity - Invalid request format

**Example (CURL):**
```bash
curl -X POST https://intelligent-classroom-saver-api.onrender.com/api/environment \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_esp32_api_key" \
  -d '{
    "room_id": "550e8400-e29b-41d4-a716-446655440000",
    "temperature": 22.5,
    "humidity": 45.3,
    "light_level": 350,
    "ac_setpoint": 24,
    "timestamp": "2026-05-27T10:30:00Z"
  }'
```

---

### 3. Get Room Configuration

**Endpoint:** `GET /api/rooms/{room_id}/config`

**Authentication:** X-API-Key (ESP32)

**Purpose:** Retrieve room configuration including capacity, access time windows, AC setpoint, lock state, and current occupancy.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| room_id | UUID | The room to retrieve configuration for |

**Response:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "capacity": 50,
  "time_windows": {
    "monday": {"start": "08:00", "end": "17:00"},
    "tuesday": {"start": "08:00", "end": "17:00"},
    "wednesday": {"start": "08:00", "end": "17:00"},
    "thursday": {"start": "08:00", "end": "17:00"},
    "friday": {"start": "08:00", "end": "17:00"}
  },
  "ac_setpoint": 24,
  "lock_state": "unlocked",
  "current_occupancy": 25
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| room_id | UUID | The room ID |
| capacity | integer | Maximum occupancy for the room |
| time_windows | object | Access time windows by day of week |
| ac_setpoint | integer | Target AC temperature in Celsius |
| lock_state | string | "locked" or "unlocked" |
| current_occupancy | integer | Current number of people in room |

**Status Codes:**
- 200 OK - Configuration retrieved successfully
- 401 Unauthorized - Missing or invalid X-API-Key
- 404 Not Found - Room not found

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/rooms/550e8400-e29b-41d4-a716-446655440000/config" \
  -H "X-API-Key: your_esp32_api_key"
```

---

### 4. Get Active Users (User Sync)

**Endpoint:** `GET /api/users`

**Authentication:** X-API-Key (ESP32)

**Purpose:** Retrieve list of all active users with their card UIDs for fast access control comparison.

**Response:**
```json
[
  {
    "uid_fast": "04D15401521ABC",
    "user_id": "550e8400-e29b-41d4-a716-446655440000",
    "role": "student",
    "name": "John Doe"
  },
  {
    "uid_fast": "04D15401521DEF",
    "user_id": "550e8400-e29b-41d4-a716-446655440001",
    "role": "staff",
    "name": "Dr. Jane Smith"
  }
]
```

**Response Array Item Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| uid_fast | string | Fast hash of the card UID for quick comparison |
| user_id | UUID | Unique user identifier |
| role | string | User role: "student", "staff", or "admin" |
| name | string | User's full name |

**Status Codes:**
- 200 OK - User list retrieved successfully
- 401 Unauthorized - Missing or invalid X-API-Key

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/users" \
  -H "X-API-Key: your_esp32_api_key"
```

---

### 5. Get Registration Status

**Endpoint:** `GET /api/registration/status`

**Authentication:** X-API-Key (ESP32)

**Purpose:** Check if a card registration session is active. ESP32 calls this when an unknown card is detected to determine if the card should be registered or denied.

**When to call:**
1. User taps card at reader
2. Card not found in ESP32 local memory and server returns "denied"
3. ESP32 calls this endpoint to check if registration is active
4. If `active: true`, call `/api/registration/uid` with the card UID
5. If `active: false`, deny access and log as unknown card

**Response (No Active Session):**
```json
{
  "active": false,
  "session_id": null
}
```

**Response (Active Session):**
```json
{
  "active": true,
  "session_id": "abc123def456"
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| active | boolean | Whether registration session is active |
| session_id | string \| null | Session ID if active |

**Status Codes:**
- 200 OK - Status retrieved successfully
- 401 Unauthorized - Missing or invalid X-API-Key

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/registration/status" \
  -H "X-API-Key: your_esp32_api_key"
```

---

### 6. Submit Registration UID

**Endpoint:** `POST /api/registration/uid`

**Authentication:** X-API-Key (ESP32)

**Purpose:** Submit a card UID during an active registration session (called when a card is tapped during registration mode). The server creates a new user account with the provided card UID.

**When to call:** 
1. User taps unknown card at reader
2. ESP32 receives "denied - Unknown card" response from `/api/access`
3. ESP32 calls `/api/registration/status` to check if registration is active
4. If active, ESP32 calls this endpoint with the card UID
5. Server creates new user and returns success

**Request Body:**
```json
{
  "uid": "04D15401521ABC"
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| uid | string | Yes | The card UID being registered (1-50 chars) |

**Response:**
```json
{
  "status": "ok",
  "message": "Card registered"
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| status | string | "ok" if successful |
| message | string | Human-readable result message |

**Status Codes:**
- 200 OK - Card registered successfully. New user account created.
- 400 Bad Request - No active registration session or session expired
- 401 Unauthorized - Missing or invalid X-API-Key
- 409 Conflict - Card UID already registered to another user, or email already exists
- 422 Unprocessable Entity - Invalid request format

**Error Handling:**
- If card is already registered: ESP32 should deny access and inform user via UI
- If session expires (5 min timeout): ESP32 should display "Registration timeout" message
- If no active session: ESP32 should deny access normally

**Example (CURL):**
```bash
curl -X POST https://intelligent-classroom-saver-api.onrender.com/api/registration/uid \
  -H "Content-Type: application/json" \
  -H "X-API-Key: your_esp32_api_key" \
  -d '{
    "uid": "04D15401521ABC"
  }'
```

---

## Frontend/User Endpoints

All frontend endpoints require Bearer token authentication (except `/api/auth/login`) and are located under `/api` prefix.

### Authentication Endpoints

#### 1. Login

**Endpoint:** `POST /api/auth/login`

**Authentication:** None (public endpoint)

**Purpose:** Authenticate user with email and password, receive JWT token.

**Request Body:**
```json
{
  "email": "user@example.com",
  "password": "password123"
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| email | string | Yes | User's email address |
| password | string | Yes | User's password |

**Response (Success):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| access_token | string | JWT token for authenticated requests |
| token_type | string | Always "bearer" |

**Status Codes:**
- 200 OK - Login successful
- 401 Unauthorized - Invalid credentials
- 422 Unprocessable Entity - Invalid request format

**Example (CURL):**
```bash
curl -X POST https://intelligent-classroom-saver-api.onrender.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "password123"
  }'
```

---

### Dashboard Endpoints

#### 1. Get Dashboard Room Data

**Endpoint:** `GET /api/dashboard/rooms/{room_id}`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "staff" or "admin" role

**Purpose:** Get real-time room status including occupancy, environment, recent access events, and lock state.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| room_id | UUID | The room to retrieve data for |

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "room_name": "Lab Room 101",
  "current_occupancy": 25,
  "capacity": 50,
  "lock_state": "unlocked",
  "ac_setpoint": 24,
  "temperature": 22.5,
  "humidity": 45.3,
  "recent_events": [
    {
      "full_name": "John Doe",
      "matric_number": "MAT001",
      "event_type": "entry",
      "timestamp": "2026-05-27T10:30:00+00:00",
      "door_state": "entry"
    },
    {
      "full_name": "Jane Smith",
      "matric_number": "MAT002",
      "event_type": "exit",
      "timestamp": "2026-05-27T10:25:00+00:00",
      "door_state": "exit"
    }
  ]
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| room_id | UUID | The room ID |
| room_name | string | Display name of the room |
| current_occupancy | integer | Current number of people in room |
| capacity | integer | Maximum capacity |
| lock_state | string | "locked" or "unlocked" |
| ac_setpoint | integer | AC target temperature |
| temperature | float \| null | Current room temperature in Celsius |
| humidity | float \| null | Current room humidity percentage |
| recent_events | array | Recent access events (see below) |

**Recent Events Item:**
| Field | Type | Description |
|-------|------|-------------|
| full_name | string \| null | Name of person if registered |
| matric_number | string \| null | Student ID if applicable |
| event_type | string | "entry" or "exit" |
| timestamp | ISO 8601 datetime | When event occurred |
| door_state | string | "entry" or "exit" |

**Status Codes:**
- 200 OK - Data retrieved successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks required role
- 404 Not Found - Room not found

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/dashboard/rooms/550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### Analytics Endpoints

#### 1. Get Energy Analytics

**Endpoint:** `GET /api/analytics/energy/{room_id}`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "staff" or "admin" role

**Purpose:** Get energy consumption analytics for a room over a date range.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| room_id | UUID | The room to get analytics for |

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| date_from | ISO 8601 datetime | Yes | Start date for analytics period |
| date_to | ISO 8601 datetime | Yes | End date for analytics period |

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "room_id": "550e8400-e29b-41d4-a716-446655440000",
  "date_from": "2026-05-01T00:00:00+00:00",
  "date_to": "2026-05-27T23:59:59+00:00",
  "runtime_hours": 156.5,
  "estimated_kwh": 423.8,
  "avg_temperature": 22.3,
  "avg_humidity": 46.2
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| room_id | UUID | The room ID |
| date_from | ISO 8601 datetime | Start of analysis period |
| date_to | ISO 8601 datetime | End of analysis period |
| runtime_hours | float | Total AC/heating runtime hours |
| estimated_kwh | float | Estimated energy consumption in kWh |
| avg_temperature | float \| null | Average temperature during period |
| avg_humidity | float \| null | Average humidity during period |

**Status Codes:**
- 200 OK - Analytics retrieved successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks required role
- 404 Not Found - Room not found

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/analytics/energy/550e8400-e29b-41d4-a716-446655440000?date_from=2026-05-01T00:00:00Z&date_to=2026-05-27T23:59:59Z" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

#### 2. Get Alerts

**Endpoint:** `GET /api/alerts`

**Authentication:** Bearer token (Required)

**Purpose:** Get list of alerts (room condition alerts). User sees only alerts relevant to their assigned rooms.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| acknowledged | boolean | No | Filter by acknowledgment status (true/false) |
| room_id | UUID | No | Filter by specific room |

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
[
  {
    "alert_id": "550e8400-e29b-41d4-a716-446655440010",
    "room_id": "550e8400-e29b-41d4-a716-446655440000",
    "alert_type": "temperature_high",
    "severity": "warning",
    "message": "Room temperature exceeds 26°C",
    "acknowledged": false,
    "triggered_at": "2026-05-27T10:30:00+00:00"
  },
  {
    "alert_id": "550e8400-e29b-41d4-a716-446655440011",
    "room_id": "550e8400-e29b-41d4-a716-446655440000",
    "alert_type": "occupancy_critical",
    "severity": "critical",
    "message": "Room occupancy exceeds 90% capacity",
    "acknowledged": true,
    "triggered_at": "2026-05-27T10:15:00+00:00"
  }
]
```

**Response Array Item Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| alert_id | UUID | Unique alert identifier |
| room_id | UUID | The room triggering the alert |
| alert_type | string | Type of alert (e.g., "temperature_high", "occupancy_critical") |
| severity | string | "warning" or "critical" |
| message | string | Human-readable alert message |
| acknowledged | boolean | Whether alert has been acknowledged |
| triggered_at | ISO 8601 datetime | When alert was triggered |

**Status Codes:**
- 200 OK - Alerts retrieved successfully
- 401 Unauthorized - Invalid or missing token

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/alerts" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Example with Filters:**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/alerts?acknowledged=false&room_id=550e8400-e29b-41d4-a716-446655440000" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

#### 3. Acknowledge Alert

**Endpoint:** `PUT /api/alerts/{alert_id}/acknowledge`

**Authentication:** Bearer token (Required)

**Purpose:** Mark an alert as acknowledged by the current user.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| alert_id | UUID | The alert to acknowledge |

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "alert_id": "550e8400-e29b-41d4-a716-446655440010",
  "acknowledged": true
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| alert_id | UUID | The acknowledged alert ID |
| acknowledged | boolean | Always true on success |

**Status Codes:**
- 200 OK - Alert acknowledged successfully
- 401 Unauthorized - Invalid or missing token
- 404 Not Found - Alert not found

**Example (CURL):**
```bash
curl -X PUT "https://intelligent-classroom-saver-api.onrender.com/api/alerts/550e8400-e29b-41d4-a716-446655440010/acknowledge" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

### Reporting Endpoints

#### 1. Get Attendance Report

**Endpoint:** `GET /api/reports/attendance`

**Authentication:** Bearer token (Required)

**Purpose:** Generate attendance report for a room and date range, optionally filtered by student or course.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| room_id | UUID | Yes | The room to generate report for |
| date_from | ISO 8601 datetime | Yes | Report start date |
| date_to | ISO 8601 datetime | Yes | Report end date |
| format | string | No | "json" (default) or "csv" |
| student_id | UUID | No | Filter by specific student |
| course_id | UUID | No | Filter by specific course |

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response (JSON Format):**
```json
[
  {
    "timestamp": "2026-05-27T10:30:00+00:00",
    "full_name": "John Doe",
    "matric_number": "MAT001",
    "course_code": "CS101",
    "event_type": "entry",
    "door_state": "entry"
  },
  {
    "timestamp": "2026-05-27T11:45:00+00:00",
    "full_name": "John Doe",
    "matric_number": "MAT001",
    "course_code": "CS101",
    "event_type": "exit",
    "door_state": "exit"
  }
]
```

**Response Array Item Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| timestamp | ISO 8601 datetime | When the access event occurred |
| full_name | string \| null | Student's full name if registered |
| matric_number | string \| null | Student ID if available |
| course_code | string \| null | Course code if available |
| event_type | string | "entry" or "exit" |
| door_state | string | "entry" or "exit" |

**Response (CSV Format):**
Returns CSV file download with same columns as JSON response.

**Status Codes:**
- 200 OK - Report generated successfully
- 401 Unauthorized - Invalid or missing token
- 404 Not Found - Room not found

**Example (CURL - JSON):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/reports/attendance?room_id=550e8400-e29b-41d4-a716-446655440000&date_from=2026-05-01T00:00:00Z&date_to=2026-05-27T23:59:59Z" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

**Example (CURL - CSV):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/reports/attendance?room_id=550e8400-e29b-41d4-a716-446655440000&date_from=2026-05-01T00:00:00Z&date_to=2026-05-27T23:59:59Z&format=csv" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -o attendance.csv
```

---

### Admin Endpoints

All admin endpoints require Bearer token with "admin" role.

#### 1. Create Card User

**Endpoint:** `POST /api/admin/cards`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "admin" role

**Purpose:** Create a new card user (e.g., for guest access or bulk registration).

**Request Body:**
```json
{
  "full_name": "John Doe",
  "email": "john.doe@example.com",
  "matric_number": "MAT001",
  "role": "student",
  "raw_card_uid": "04D15401521ABC",
  "department": "Computer Science",
  "level": 200,
  "assigned_rooms": [
    "550e8400-e29b-41d4-a716-446655440000",
    "550e8400-e29b-41d4-a716-446655440001"
  ]
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| full_name | string | Yes | User's full name (1-255 chars) |
| email | string | Yes | User's email address (3-255 chars) |
| matric_number | string | No | Student/staff ID (max 50 chars) |
| role | string | Yes | "student", "staff", or "admin" |
| raw_card_uid | string | Yes | The card UID to register (1-50 chars) |
| department | string | No | Department name (max 100 chars) |
| level | integer | No | Academic level (e.g., 100, 200, 300) |
| assigned_rooms | array | No | List of room UUIDs the user can access |

**Response:**
```json
{
  "user_id": "550e8400-e29b-41d4-a716-446655440050"
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| user_id | UUID | The newly created user's ID |

**Status Codes:**
- 200 OK - User created successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks admin role
- 422 Unprocessable Entity - Invalid request format

**Example (CURL):**
```bash
curl -X POST https://intelligent-classroom-saver-api.onrender.com/api/admin/cards \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "full_name": "John Doe",
    "email": "john.doe@example.com",
    "matric_number": "MAT001",
    "role": "student",
    "raw_card_uid": "04D15401521ABC",
    "department": "Computer Science",
    "level": 200,
    "assigned_rooms": []
  }'
```

---

#### 2. Update Card Status

**Endpoint:** `PUT /api/admin/cards/{user_id}/status`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "admin" role

**Purpose:** Activate or suspend a user's card access.

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| user_id | UUID | The user whose card status is being updated |

**Request Body:**
```json
{
  "status": "suspended"
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| status | string | Yes | "active" or "suspended" |

**Response:**
```json
{
  "status": "ok"
}
```

**Status Codes:**
- 200 OK - Card status updated successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks admin role
- 404 Not Found - User not found

**Example (CURL):**
```bash
curl -X PUT "https://intelligent-classroom-saver-api.onrender.com/api/admin/cards/550e8400-e29b-41d4-a716-446655440050/status" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "status": "suspended"
  }'
```

---

#### 3. Update Room Time Windows

**Endpoint:** `PUT /api/admin/rooms/{room_id}/windows`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "admin" role

**Purpose:** Update when users are allowed to access a room (e.g., class hours).

**Path Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| room_id | UUID | The room to update |

**Request Body:**
```json
{
  "time_windows": {
    "monday": {"start": "08:00", "end": "17:00"},
    "tuesday": {"start": "08:00", "end": "17:00"},
    "wednesday": {"start": "08:00", "end": "17:00"},
    "thursday": {"start": "08:00", "end": "17:00"},
    "friday": {"start": "08:00", "end": "17:00"},
    "saturday": null,
    "sunday": null
  }
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| time_windows | object | Yes | Daily access windows by day name. null = closed all day |

**Response:**
```json
{
  "status": "ok"
}
```

**Status Codes:**
- 200 OK - Time windows updated successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks admin role
- 404 Not Found - Room not found

**Example (CURL):**
```bash
curl -X PUT "https://intelligent-classroom-saver-api.onrender.com/api/admin/rooms/550e8400-e29b-41d4-a716-446655440000/windows" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "time_windows": {
      "monday": {"start": "08:00", "end": "17:00"},
      "tuesday": {"start": "08:00", "end": "17:00"},
      "wednesday": {"start": "08:00", "end": "17:00"},
      "thursday": {"start": "08:00", "end": "17:00"},
      "friday": {"start": "08:00", "end": "17:00"}
    }
  }'
```

---

#### 4. List Users (Paginated)

**Endpoint:** `GET /api/admin/users`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "admin" role

**Purpose:** Get paginated list of all users in the system.

**Query Parameters:**
| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| page | integer | No | Page number (default 1, min 1) |
| limit | integer | No | Results per page (default 20, min 1, max 100) |

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "page": 1,
  "limit": 20,
  "total": 45,
  "items": [
    {
      "user_id": "550e8400-e29b-41d4-a716-446655440000",
      "full_name": "John Doe",
      "email": "john.doe@example.com",
      "matric_number": "MAT001",
      "role": "student",
      "card_status": "active",
      "department": "Computer Science",
      "level": 200,
      "assigned_rooms": [
        "550e8400-e29b-41d4-a716-446655440000",
        "550e8400-e29b-41d4-a716-446655440001"
      ],
      "created_at": "2026-05-01T10:00:00+00:00"
    }
  ]
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| page | integer | Current page number |
| limit | integer | Results per page |
| total | integer | Total number of users |
| items | array | User objects (see UserPublic schema) |

**User Object Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| user_id | UUID | Unique user identifier |
| full_name | string | User's full name |
| email | string | User's email |
| matric_number | string \| null | Student/staff ID |
| role | string | "student", "staff", or "admin" |
| card_status | string | "active" or "suspended" |
| department | string \| null | User's department |
| level | integer \| null | Academic level |
| assigned_rooms | array | UUIDs of accessible rooms |
| created_at | ISO 8601 datetime | Account creation time |

**Status Codes:**
- 200 OK - User list retrieved successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks admin role

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/admin/users?page=1&limit=20" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

#### 5. Start Card Registration Session

**Endpoint:** `POST /api/admin/registration/start`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "admin" role

**Purpose:** Initiate a card registration session from the web portal. ESP32 devices will receive this status and display registration mode UI.

**Request Body:**
```json
{
  "full_name": "Jane Smith",
  "email": "jane.smith@example.com",
  "role": "staff",
  "matric_number": null,
  "department": "Physics",
  "level": null,
  "assigned_rooms": [
    "550e8400-e29b-41d4-a716-446655440000"
  ]
}
```

**Request Parameters:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| full_name | string | Yes | New user's full name (1-255 chars) |
| email | string | Yes | New user's email (3-255 chars) |
| role | string | Yes | "student", "staff", or "admin" |
| matric_number | string | No | Student/staff ID (max 50 chars) |
| department | string | No | Department (max 100 chars) |
| level | integer | No | Academic level |
| assigned_rooms | array | No | Room UUIDs the user can access |

**Response:**
```json
{
  "session_id": "abc123def456",
  "status": "ok"
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| session_id | string | Unique registration session identifier |
| status | string | Always "ok" on success |

**Status Codes:**
- 200 OK - Registration session started successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks admin role

**Example (CURL):**
```bash
curl -X POST https://intelligent-classroom-saver-api.onrender.com/api/admin/registration/start \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..." \
  -d '{
    "full_name": "Jane Smith",
    "email": "jane.smith@example.com",
    "role": "staff",
    "department": "Physics",
    "assigned_rooms": []
  }'
```

---

#### 6. Get Registration Session Status (Admin)

**Endpoint:** `GET /api/admin/registration/status`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "admin" role

**Purpose:** Poll registration session status from web portal. Frontend uses this to:
- Check if registration is in progress
- Display "Waiting for card tap..." status
- Show the received card UID when tapped
- Display "Registration complete!" when done

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response (No Active Session):**
```json
{
  "active": false,
  "completed": false
}
```

**Response (Active Session - Waiting for Card):**
```json
{
  "active": true,
  "completed": false,
  "session_id": "abc123def456",
  "full_name": "Jane Smith",
  "received_uid": null
}
```

**Response (Card Tapped - Registration Complete):**
```json
{
  "active": true,
  "completed": true,
  "session_id": "abc123def456",
  "full_name": "Jane Smith",
  "received_uid": "04D15401521ABC"
}
```

**Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| active | boolean | Whether a registration session is active |
| completed | boolean | Whether the card has been tapped and user created |
| session_id | string \| null | Unique registration session ID if active |
| full_name | string \| null | Name of user being registered if active |
| received_uid | string \| null | The card UID that was tapped (only present if completed=true) |

**Frontend Polling Pattern:**
1. After calling `/api/admin/registration/start`, poll this endpoint every 2-3 seconds
2. Display "Waiting for card tap..." while `completed` is false
3. When `received_uid` appears, display it: "Card UID received: 04D15401521ABC"
4. Show "User created successfully!" confirmation message
5. Optionally retry registration or dismiss the dialog

**Status Codes:**
- 200 OK - Status retrieved successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks admin role

**Example (CURL):**
```bash
curl -X GET "https://intelligent-classroom-saver-api.onrender.com/api/admin/registration/status" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

#### 7. Cancel Registration Session

**Endpoint:** `DELETE /api/admin/registration`

**Authentication:** Bearer token (Required)

**Authorization:** User must have "admin" role

**Purpose:** Cancel any active registration session.

**Headers:**
```
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "status": "ok"
}
```

**Status Codes:**
- 200 OK - Registration session cancelled successfully
- 401 Unauthorized - Invalid or missing token
- 403 Forbidden - User lacks admin role

**Example (CURL):**
```bash
curl -X DELETE "https://intelligent-classroom-saver-api.onrender.com/api/admin/registration" \
  -H "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
```

---

## Error Handling

All errors follow a consistent JSON response format:

**Error Response Format:**
```json
{
  "status": "error",
  "code": 400,
  "message": "Descriptive error message"
}
```

**Error Response Parameters:**
| Field | Type | Description |
|-------|------|-------------|
| status | string | Always "error" for error responses |
| code | integer | HTTP status code |
| message | string | Human-readable error message |

**Exception Types:**

- **HTTPException**: Custom HTTP errors (401, 403, 404, etc.)
- **RequestValidationError**: Pydantic validation errors (422)
- **General Exceptions**: Unhandled errors (500)

---

## Status Codes

### Success Codes
| Code | Description |
|------|-------------|
| 200 | OK - Request successful |

### Client Error Codes
| Code | Description |
|------|-------------|
| 401 | Unauthorized - Missing or invalid authentication |
| 403 | Forbidden - Authenticated but insufficient permissions |
| 404 | Not Found - Resource does not exist |
| 422 | Unprocessable Entity - Invalid request format or data |

### Server Error Codes
| Code | Description |
|------|-------------|
| 500 | Internal Server Error - Unhandled server error |

---

## Common Implementation Notes

### UUID Format
All UUIDs in the API follow the standard UUID v4 format:
```
550e8400-e29b-41d4-a716-446655440000
```

### DateTime Format
All timestamps use ISO 8601 format with timezone information:
```
2026-05-27T10:30:00+00:00
```

### Pagination
Admin endpoints support pagination with:
- `page`: 1-indexed page number
- `limit`: Results per page (1-100 range)

### Token Expiration
JWT tokens expire after the configured duration (default 30 minutes). Frontend should:
1. Store token securely
2. Check expiration before making requests
3. Re-authenticate if token expires

### Rate Limiting
Currently not implemented but can be added. ESP32 devices should implement reasonable request intervals:
- Access events: On-demand
- Environment events: Every 5-10 minutes
- User sync: Every 30 minutes
- Config requests: On startup and when needed

### CORS
CORS is enabled with configurable origins via `CORS_ALLOW_ORIGINS` environment variable.

---

## Environment Variables

Required environment variables for backend:

```env
# Database
DATABASE_URL=postgresql+asyncpg://user:password@localhost/intelligent_classroom_saver

# JWT
JWT_SECRET_KEY=your_super_secret_key_at_least_32_characters_long
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# ESP32
ESP32_API_KEY=your_esp32_api_key_here

# Optional
DEFAULT_CARD_PASSWORD=default_password
CORS_ALLOW_ORIGINS=*
```

---

## Quick Integration Guide for ESP32 Firmware

When implementing ESP32 firmware based on this API:

### 1. **Initialization & Sync**
   - On startup, call `GET /api/users` to populate local card UID cache
   - Store `uid_fast` and `user_id` in ESP32 memory for fast lookups
   - Periodically refresh (every 30 minutes) to get new/updated users

### 2. **Card Access Decision Flow**
   ```
   When card tapped at reader:
   1. Extract card UID from NFC reader
   2. Check ESP32 local memory for card UID
   3. If found locally:
       - Unlock door immediately (firmware decision)
       - Send to server: POST /api/access
       - Server returns "granted", log entry/exit
   4. If NOT found locally:
       - Send to server: POST /api/access
       - Parse response:
           - If "granted": Unlock door (user just synced or recovered)
           - If "denied": Check for active registration
   ```

### 3. **Registration Flow for Unknown Cards**
   ```
   When /api/access returns "denied - Unknown card":
   1. Poll GET /api/registration/status
   2. If active == true:
       - Display "Registration Active" message on UI
       - Send card UID: POST /api/registration/uid
       - Handle response:
           - If 200: Display "Card Registered!" and unlock door
           - If 409: Display "Card already registered"
           - If 400: Display "Registration expired, try again"
   3. If active == false:
       - Deny access (keep door locked)
       - Display "Access Denied - Unknown Card" on UI
       - Log attempt
   ```

### 4. **Environment Monitoring**
   - Periodically send sensor readings: `POST /api/environment` (every 5-10 min)
   - Include temperature, humidity, light_level, ac_setpoint
   - Server uses this to trigger alerts and track energy

### 5. **Configuration Management**
   - On startup, get room config: `GET /api/rooms/{room_id}/config`
   - Cache locally: `capacity`, `time_windows`, `ac_setpoint`, `lock_state`
   - Periodically refresh (every hour) to get admin updates

### 6. **Error Handling**
   - **401 Unauthorized**: Invalid X-API-Key, check config
   - **409 Conflict**: Card already registered, show specific error to user
   - **Network errors**: Implement retry logic with exponential backoff
   - **Session timeout** (5 min): Registration expires, user must restart

### 7. **Recommended Polling Intervals**
   - User sync (`/api/users`): 30 minutes
   - Room config (`/api/rooms/{id}/config`): On startup + on-demand
   - Registration status (`/api/registration/status`): Only when unknown card detected
   - Access events (`/api/access`): On-demand (immediate on card tap)
   - Environment events (`/api/environment`): 5-10 minutes

---

## Quick Integration Guide for Frontend Bot

When implementing the frontend based on this API:

1. **Authentication Flow:**
   - POST to `/api/auth/login` with email/password
   - Store returned `access_token`
   - Add `Authorization: Bearer <token>` header to all subsequent requests

2. **Dashboard Implementation:**
   - GET `/api/dashboard/rooms/{room_id}` for real-time room data
   - Poll at 5-10 second intervals for live updates
   - Display `current_occupancy`, `temperature`, `humidity`, `recent_events`

3. **Alerts Handling:**
   - GET `/api/alerts` to fetch unacknowledged alerts
   - Poll at 10-30 second intervals
   - PUT `/api/alerts/{alert_id}/acknowledge` when user clicks acknowledge
   - Show severity-based styling (warning/critical)

4. **Reports:**
   - Allow users to select date range and room
   - GET `/api/reports/attendance` with filters
   - Support both JSON display and CSV download

5. **Admin Panel - User Registration:**
   
   **Registration Flow:**
   ```
   1. Admin fills registration form:
      - Full name, email, role, department, level, assigned rooms
   2. Admin clicks "Register User" button
   3. Frontend: POST /api/admin/registration/start with form data
   4. Start polling: GET /api/admin/registration/status every 2-3 seconds
   5. While polling, display: "Waiting for card tap..."
   6. When completed=true received:
      - Display: "Card registered: [received_uid]"
      - Show: "User created successfully!"
      - Allow user to close dialog or register another user
   ```
   
   **Error Handling:**
   - If poll returns `active: false` but `completed: false`: Session expired, retry
   - Display timeout message after 5+ minutes
   - Handle network errors gracefully with retry logic
   
   **Display States:**
   - Waiting state: "Enter user details and click Register. User will be created when card is tapped."
   - Tapping state: "Waiting for card tap... (keep card near reader)"
   - Success state: "✓ Card UID: 04D15401521ABC - User created!"
   - Error state: "✗ Error: [error message from server]"

6. **Error Handling:**
   - Check for 401 status and redirect to login
   - Display error messages from response `message` field
   - Retry failed requests with exponential backoff

---

## Support

For issues or questions about API endpoints, refer to the router implementations:
- ESP32: [ics_backend/routers/esp32.py](ics_backend/routers/esp32.py)
- Auth: [ics_backend/routers/auth.py](ics_backend/routers/auth.py)
- Dashboard: [ics_backend/routers/dashboard.py](ics_backend/routers/dashboard.py)
- Analytics: [ics_backend/routers/analytics.py](ics_backend/routers/analytics.py)
- Reports: [ics_backend/routers/reports.py](ics_backend/routers/reports.py)
- Admin: [ics_backend/routers/admin.py](ics_backend/routers/admin.py)
