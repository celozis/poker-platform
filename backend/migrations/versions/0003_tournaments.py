"""Club tournaments with their blind structure and rules.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tournaments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("buy_in", sa.Integer(), nullable=False),
        sa.Column("starting_stack", sa.Integer(), nullable=False),
        sa.Column("structure", postgresql.JSONB(), nullable=False),
        sa.Column("reentry_until_level", sa.Integer(), nullable=True),
        sa.Column("addon_at_level", sa.Integer(), nullable=True),
        sa.Column("late_registration_until_level", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
    )
    op.create_index("ix_tournaments_club_id", "tournaments", ["club_id"])


def downgrade() -> None:
    op.drop_table("tournaments")
