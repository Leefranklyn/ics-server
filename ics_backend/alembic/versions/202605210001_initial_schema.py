"""initial schema

Revision ID: 202605210001
Revises:
Create Date: 2026-05-21 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "202605210001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.create_table(
        "users",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("matric_number", sa.String(length=50), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("card_uid_hash", sa.String(length=255), nullable=True),
        sa.Column("card_status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("department", sa.String(length=100), nullable=True),
        sa.Column("level", sa.Integer(), nullable=True),
        sa.Column("assigned_rooms", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("card_status IN ('active', 'suspended')", name=op.f("ck_users_card_status_valid")),
        sa.CheckConstraint("role IN ('student', 'staff', 'admin')", name=op.f("ck_users_role_valid")),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("matric_number", name=op.f("uq_users_matric_number")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=False)
    op.create_table(
        "rooms",
        sa.Column("room_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("room_name", sa.String(length=100), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("assigned_staff", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("lock_state", sa.String(length=20), server_default=sa.text("'locked'"), nullable=False),
        sa.Column("current_occupancy", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ac_setpoint", sa.Integer(), server_default=sa.text("24"), nullable=False),
        sa.Column("time_windows", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("lock_state IN ('locked', 'unlocked')", name=op.f("ck_rooms_lock_state_valid")),
        sa.PrimaryKeyConstraint("room_id", name=op.f("pk_rooms")),
    )
    op.create_table(
        "courses",
        sa.Column("course_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("course_code", sa.String(length=20), nullable=False),
        sa.Column("course_name", sa.String(length=255), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lecturer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("schedule", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("semester", sa.String(length=30), nullable=True),
        sa.Column("academic_year", sa.String(length=20), nullable=True),
        sa.ForeignKeyConstraint(["lecturer_id"], ["users.user_id"], name=op.f("fk_courses_lecturer_id_users")),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name=op.f("fk_courses_room_id_rooms")),
        sa.PrimaryKeyConstraint("course_id", name=op.f("pk_courses")),
    )
    op.create_table(
        "alerts",
        sa.Column("alert_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("alert_type", sa.String(length=50), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("acknowledged", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("triggered_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("severity IN ('warning', 'critical')", name=op.f("ck_alerts_severity_valid")),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name=op.f("fk_alerts_room_id_rooms")),
        sa.PrimaryKeyConstraint("alert_id", name=op.f("pk_alerts")),
    )
    op.create_index("ix_alerts_room_ack_triggered", "alerts", ["room_id", "acknowledged", "triggered_at"], unique=False)
    op.create_table(
        "enrollments",
        sa.Column("enrollment_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("status", sa.String(length=20), server_default=sa.text("'active'"), nullable=False),
        sa.CheckConstraint("status IN ('active', 'dropped', 'completed')", name=op.f("ck_enrollments_enrollment_status_valid")),
        sa.ForeignKeyConstraint(["course_id"], ["courses.course_id"], name=op.f("fk_enrollments_course_id_courses")),
        sa.ForeignKeyConstraint(["student_id"], ["users.user_id"], name=op.f("fk_enrollments_student_id_users")),
        sa.PrimaryKeyConstraint("enrollment_id", name=op.f("pk_enrollments")),
        sa.UniqueConstraint("student_id", "course_id", name="uq_enrollments_student_course"),
    )
    op.create_table(
        "environment_log",
        sa.Column("env_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("humidity", sa.Float(), nullable=False),
        sa.Column("light_level", sa.Integer(), nullable=False),
        sa.Column("ac_setpoint", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name=op.f("fk_environment_log_room_id_rooms")),
        sa.PrimaryKeyConstraint("env_id", name=op.f("pk_environment_log")),
    )
    op.create_index("ix_environment_log_room_timestamp", "environment_log", ["room_id", "timestamp"], unique=False)
    op.create_table(
        "occupancy_log",
        sa.Column("occ_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("occupancy_count", sa.Integer(), nullable=False),
        sa.Column("ac_setpoint", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name=op.f("fk_occupancy_log_room_id_rooms")),
        sa.PrimaryKeyConstraint("occ_id", name=op.f("pk_occupancy_log")),
    )
    op.create_index("ix_occupancy_log_room_timestamp", "occupancy_log", ["room_id", "timestamp"], unique=False)
    op.create_table(
        "access_log",
        sa.Column("log_id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=20), nullable=False),
        sa.Column("card_uid", sa.String(length=50), nullable=False),
        sa.Column("door_state", sa.String(length=20), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("synced_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.CheckConstraint("door_state IN ('opened', 'closed')", name=op.f("ck_access_log_door_state_valid")),
        sa.CheckConstraint("event_type IN ('entry', 'exit', 'denied')", name=op.f("ck_access_log_event_type_valid")),
        sa.ForeignKeyConstraint(["course_id"], ["courses.course_id"], name=op.f("fk_access_log_course_id_courses")),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.room_id"], name=op.f("fk_access_log_room_id_rooms")),
        sa.ForeignKeyConstraint(["user_id"], ["users.user_id"], name=op.f("fk_access_log_user_id_users")),
        sa.PrimaryKeyConstraint("log_id", name=op.f("pk_access_log")),
    )
    op.create_index("ix_access_log_course_timestamp", "access_log", ["course_id", "timestamp"], unique=False)
    op.create_index("ix_access_log_room_timestamp", "access_log", ["room_id", "timestamp"], unique=False)
    op.create_index("ix_access_log_user_timestamp", "access_log", ["user_id", "timestamp"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_access_log_user_timestamp", table_name="access_log")
    op.drop_index("ix_access_log_room_timestamp", table_name="access_log")
    op.drop_index("ix_access_log_course_timestamp", table_name="access_log")
    op.drop_table("access_log")
    op.drop_index("ix_occupancy_log_room_timestamp", table_name="occupancy_log")
    op.drop_table("occupancy_log")
    op.drop_index("ix_environment_log_room_timestamp", table_name="environment_log")
    op.drop_table("environment_log")
    op.drop_table("enrollments")
    op.drop_index("ix_alerts_room_ack_triggered", table_name="alerts")
    op.drop_table("alerts")
    op.drop_table("courses")
    op.drop_table("rooms")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
