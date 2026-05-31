"""add attendance sessions

Revision ID: 202605310001
Revises: 202605270001
Create Date: 2026-05-31 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605310001"
down_revision = "202605270001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_access_log_event_type_valid"), "access_log", type_="check")
    op.create_check_constraint(
        op.f("ck_access_log_event_type_valid"),
        "access_log",
        "event_type IN ('entry', 'exit', 'denied', 'attendance')",
    )

    op.create_table(
        "attendance_sessions",
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("opened_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_name", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'closed')",
            name=op.f("ck_attendance_sessions_attendance_session_status_valid"),
        ),
        sa.ForeignKeyConstraint(["course_id"], ["courses.course_id"], name=op.f("fk_attendance_sessions_course_id_courses")),
        sa.ForeignKeyConstraint(["opened_by"], ["users.user_id"], name=op.f("fk_attendance_sessions_opened_by_users")),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name=op.f("fk_attendance_sessions_room_id_rooms")),
        sa.PrimaryKeyConstraint("session_id", name=op.f("pk_attendance_sessions")),
    )
    op.create_index(
        "ix_attendance_sessions_course_started_at",
        "attendance_sessions",
        ["course_id", "started_at"],
        unique=False,
    )
    op.create_index("ix_attendance_sessions_room_status", "attendance_sessions", ["room_id", "status"], unique=False)
    op.create_index(
        "uq_attendance_sessions_active_room",
        "attendance_sessions",
        ["room_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )

    op.create_table(
        "attendance_records",
        sa.Column(
            "attendance_record_id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("marked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("marked_by_card_uid", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["course_id"],
            ["courses.course_id"],
            name=op.f("fk_attendance_records_course_id_courses"),
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name=op.f("fk_attendance_records_room_id_rooms")),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["attendance_sessions.session_id"],
            name=op.f("fk_attendance_records_session_id_attendance_sessions"),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name=op.f("fk_attendance_records_user_id_users")),
        sa.PrimaryKeyConstraint("attendance_record_id", name=op.f("pk_attendance_records")),
        sa.UniqueConstraint("session_id", "user_id", name="uq_attendance_records_session_user"),
    )
    op.create_index(
        "ix_attendance_records_course_marked_at",
        "attendance_records",
        ["course_id", "marked_at"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_records_room_marked_at",
        "attendance_records",
        ["room_id", "marked_at"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_records_session_marked_at",
        "attendance_records",
        ["session_id", "marked_at"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_records_user_marked_at",
        "attendance_records",
        ["user_id", "marked_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_attendance_records_user_marked_at", table_name="attendance_records")
    op.drop_index("ix_attendance_records_session_marked_at", table_name="attendance_records")
    op.drop_index("ix_attendance_records_room_marked_at", table_name="attendance_records")
    op.drop_index("ix_attendance_records_course_marked_at", table_name="attendance_records")
    op.drop_table("attendance_records")
    op.drop_index("uq_attendance_sessions_active_room", table_name="attendance_sessions")
    op.drop_index("ix_attendance_sessions_room_status", table_name="attendance_sessions")
    op.drop_index("ix_attendance_sessions_course_started_at", table_name="attendance_sessions")
    op.drop_table("attendance_sessions")

    op.drop_constraint(op.f("ck_access_log_event_type_valid"), "access_log", type_="check")
    op.create_check_constraint(
        op.f("ck_access_log_event_type_valid"),
        "access_log",
        "event_type IN ('entry', 'exit', 'denied')",
    )
