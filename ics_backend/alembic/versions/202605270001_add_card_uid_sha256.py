"""add card_uid_sha256 column

Revision ID: 202605270001
Revises: 202605210001
Create Date: 2026-05-27 00:00:00.000000
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "202605270001"
down_revision = "202605210001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("card_uid_sha256", sa.String(length=64), nullable=True))
    op.create_index(op.f("ix_users_card_uid_sha256"), "users", ["card_uid_sha256"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_card_uid_sha256"), table_name="users")
    op.drop_column("users", "card_uid_sha256")
