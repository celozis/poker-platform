"""Early closing: the admin closes a tournament's registration to players, or its late
registration, before the rules would.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nothing has been closed early until now.
    for column in ("registration_closed_to_players", "late_registration_closed_early"):
        op.add_column(
            "tournaments", sa.Column(column, sa.Boolean(), nullable=False, server_default=sa.false())
        )
        op.alter_column("tournaments", column, server_default=None)


def downgrade() -> None:
    op.drop_column("tournaments", "late_registration_closed_early")
    op.drop_column("tournaments", "registration_closed_to_players")
