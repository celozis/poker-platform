"""The tournament cashier: buy-ins, re-entries and add-ons paid in cash or by card, and the price
of an add-on.

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("addon_price", sa.Integer()))
    # Tournaments made before add-ons had a price: an add-on costs as much as the buy-in.
    op.execute("UPDATE tournaments SET addon_price = buy_in WHERE addon_at_level IS NOT NULL")
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=False),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("admin_id", sa.Integer(), sa.ForeignKey("admins.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("payment_method", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "reverses_id",
            sa.Integer(),
            sa.ForeignKey("transactions.id"),
            nullable=True,
            unique=True,
        ),
        sa.Column("replaces_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=True),
    )
    op.create_index("ix_transactions_club_id", "transactions", ["club_id"])
    op.create_index("ix_transactions_tournament_id", "transactions", ["tournament_id"])
    op.create_index("ix_transactions_player_id", "transactions", ["player_id"])


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_column("tournaments", "addon_price")
