"""When the bot reminded the player of the tournament and sent them their result.

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("registrations", sa.Column("reminded_at", sa.DateTime(timezone=True)))
    op.add_column("registrations", sa.Column("result_sent_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    op.drop_column("registrations", "result_sent_at")
    op.drop_column("registrations", "reminded_at")
