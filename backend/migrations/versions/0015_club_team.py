"""The club's team: an admin removed from it is marked, not deleted, since the cashier and the
action log point at them. The league's changes to a club (its name, its owners) are logged as
done by the league.

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-03

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("admins", sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True))
    # Everything logged until now was done by an admin or a player.
    op.add_column(
        "action_log",
        sa.Column("by_league", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.alter_column("action_log", "by_league", server_default=None)


def downgrade() -> None:
    op.drop_column("action_log", "by_league")
    op.drop_column("admins", "removed_at")
