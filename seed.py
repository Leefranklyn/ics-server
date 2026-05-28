from __future__ import annotations

import asyncio

from sqlalchemy import select, text

from ics_backend.database import AsyncSessionLocal, Base, engine
from ics_backend.models import Course, Enrollment, Room, User
from ics_backend.services.card import hash_secret, sha256_uid


RAW_CARD_UIDS = {
    "staff_ade": "ICS-STAFF-ADE-001",
    "staff_okafor": "ICS-STAFF-OKAFOR-002",
    "student_amina": "ICS-STU-AMINA-101",
    "student_chinedu": "ICS-STU-CHINEDU-102",
    "student_tolani": "ICS-STU-TOLANI-103",
    "student_zainab": "ICS-STU-ZAINAB-104",
    "student_emeka": "ICS-STU-EMEKA-105",
}


ROOM_WINDOWS = {
    "mon": {"open": "08:00", "close": "20:00"},
    "tue": {"open": "08:00", "close": "20:00"},
    "wed": {"open": "08:00", "close": "20:00"},
    "thu": {"open": "08:00", "close": "20:00"},
    "fri": {"open": "08:00", "close": "18:00"},
}


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        csc_lab = await get_or_create_room(db, "CSC Lab", 40)
        physics_lab = await get_or_create_room(db, "Physics Lab", 35)
        lecture_hall = await get_or_create_room(db, "Lecture Hall A", 120)
        await db.flush()

        print("Rooms created:")
        print(f"- CSC Lab (capacity: 40)")
        print(f"- Physics Lab (capacity: 35)")
        print(f"- Lecture Hall A (capacity: 120)")

        admin = await get_or_create_user(
            db,
            full_name="ICS Administrator",
            email="admin@ics.edu",
            password="admin123",
            role="admin",
            department="ICT",
            assigned_rooms=[str(csc_lab.room_id), str(physics_lab.room_id), str(lecture_hall.room_id)],
        )
        staff_ade = await get_or_create_user(
            db,
            full_name="Dr. Ade Musa",
            email="ade.musa@ics.edu",
            password="staff123",
            role="staff",
            raw_card_uid=RAW_CARD_UIDS["staff_ade"],
            department="Computer Science",
            assigned_rooms=[str(csc_lab.room_id), str(lecture_hall.room_id)],
        )
        staff_okafor = await get_or_create_user(
            db,
            full_name="Dr. Nneka Okafor",
            email="nneka.okafor@ics.edu",
            password="staff123",
            role="staff",
            raw_card_uid=RAW_CARD_UIDS["staff_okafor"],
            department="Physics",
            assigned_rooms=[str(physics_lab.room_id)],
        )
        await db.flush()

        csc_lab.assigned_staff = [str(admin.user_id), str(staff_ade.user_id)]
        physics_lab.assigned_staff = [str(admin.user_id), str(staff_okafor.user_id)]
        lecture_hall.assigned_staff = [str(admin.user_id), str(staff_ade.user_id)]

        course_1 = await get_or_create_course(
            db,
            course_code="CSC 214",
            course_name="Data Structures",
            room=csc_lab,
            lecturer=staff_ade,
            schedule={"day": "Monday", "start_time": "09:00", "duration_mins": 90},
            semester="Rain",
            academic_year="2025/2026",
        )
        course_2 = await get_or_create_course(
            db,
            course_code="PHY 202",
            course_name="Electricity and Magnetism",
            room=physics_lab,
            lecturer=staff_okafor,
            schedule={"day": "Tuesday", "start_time": "11:00", "duration_mins": 120},
            semester="Rain",
            academic_year="2025/2026",
        )

        students = [
            await get_or_create_user(
                db,
                full_name="Amina Bello",
                email="amina.bello@student.ics.edu",
                password="student123",
                role="student",
                raw_card_uid=RAW_CARD_UIDS["student_amina"],
                matric_number="ICS/2023/001",
                department="Computer Science",
                level=300,
            ),
            await get_or_create_user(
                db,
                full_name="Chinedu Eze",
                email="chinedu.eze@student.ics.edu",
                password="student123",
                role="student",
                raw_card_uid=RAW_CARD_UIDS["student_chinedu"],
                matric_number="ICS/2023/002",
                department="Computer Science",
                level=300,
            ),
            await get_or_create_user(
                db,
                full_name="Tolani Adebayo",
                email="tolani.adebayo@student.ics.edu",
                password="student123",
                role="student",
                raw_card_uid=RAW_CARD_UIDS["student_tolani"],
                matric_number="ICS/2024/003",
                department="Computer Science",
                level=200,
            ),
            await get_or_create_user(
                db,
                full_name="Zainab Umar",
                email="zainab.umar@student.ics.edu",
                password="student123",
                role="student",
                raw_card_uid=RAW_CARD_UIDS["student_zainab"],
                matric_number="PHY/2024/004",
                department="Physics",
                level=200,
            ),
            await get_or_create_user(
                db,
                full_name="Emeka Nwosu",
                email="emeka.nwosu@student.ics.edu",
                password="student123",
                role="student",
                raw_card_uid=RAW_CARD_UIDS["student_emeka"],
                matric_number="PHY/2023/005",
                department="Physics",
                level=300,
            ),
        ]
        await db.flush()

        for student in students[:3]:
            await get_or_create_enrollment(db, student, course_1)
        for student in students[2:]:
            await get_or_create_enrollment(db, student, course_2)

        await db.commit()

    print("Seed complete.")
    print("Admin login: admin@ics.edu / admin123")
    print("Staff login password: staff123")
    print("Student login password: student123")
    print("Raw card UIDs for hardware testing:")
    for label, uid in RAW_CARD_UIDS.items():
        print(f"- {label}: {uid}")


async def get_or_create_room(db, room_name: str, capacity: int) -> Room:
    result = await db.execute(select(Room).where(Room.room_name == room_name))
    room = result.scalar_one_or_none()
    if room is not None:
        return room
    room = Room(room_name=room_name, capacity=capacity, time_windows=ROOM_WINDOWS)
    db.add(room)
    await db.flush()
    return room


async def get_or_create_user(
    db,
    *,
    full_name: str,
    email: str,
    password: str,
    role: str,
    raw_card_uid: str | None = None,
    matric_number: str | None = None,
    department: str | None = None,
    level: int | None = None,
    assigned_rooms: list[str] | None = None,
) -> User:
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is not None:
        return user
    user = User(
        full_name=full_name,
        email=email,
        matric_number=matric_number,
        password_hash=hash_secret(password),
        role=role,
        card_uid_hash=hash_secret(raw_card_uid) if raw_card_uid else None,
        card_uid_sha256=sha256_uid(raw_card_uid) if raw_card_uid else None,
        card_status="active",
        department=department,
        level=level,
        assigned_rooms=assigned_rooms or [],
    )
    db.add(user)
    await db.flush()
    return user


async def get_or_create_course(
    db,
    *,
    course_code: str,
    course_name: str,
    room: Room,
    lecturer: User,
    schedule: dict[str, object],
    semester: str,
    academic_year: str,
) -> Course:
    result = await db.execute(select(Course).where(Course.course_code == course_code, Course.academic_year == academic_year))
    course = result.scalar_one_or_none()
    if course is not None:
        return course
    course = Course(
        course_code=course_code,
        course_name=course_name,
        room_id=room.room_id,
        lecturer_id=lecturer.user_id,
        schedule=schedule,
        semester=semester,
        academic_year=academic_year,
    )
    db.add(course)
    await db.flush()
    return course


async def get_or_create_enrollment(db, student: User, course: Course) -> Enrollment:
    result = await db.execute(
        select(Enrollment).where(Enrollment.student_id == student.user_id, Enrollment.course_id == course.course_id)
    )
    enrollment = result.scalar_one_or_none()
    if enrollment is not None:
        return enrollment
    enrollment = Enrollment(student_id=student.user_id, course_id=course.course_id, status="active")
    db.add(enrollment)
    await db.flush()
    return enrollment


if __name__ == "__main__":
    asyncio.run(main())
