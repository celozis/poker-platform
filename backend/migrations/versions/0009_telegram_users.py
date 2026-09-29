"""The Telegram bot's users: their consent, the player they are linked to and their club.

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_users",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=True, unique=True
        ),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("telegram_users")
