"""Running a tournament: seats per table, the blind clock, and where each player sits or finished.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tournaments",
        sa.Column("seats_per_table", sa.Integer(), nullable=False, server_default="9"),
    )
    op.add_column("tournaments", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("tournaments", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.add_column("tournaments", sa.Column("clock_item", sa.Integer()))
    op.add_column("tournaments", sa.Column("clock_ends_at", sa.DateTime(timezone=True)))
    op.add_column("tournaments", sa.Column("clock_remaining", sa.Interval()))

    op.add_column("registrations", sa.Column("table_number", sa.Integer()))
    op.add_column("registrations", sa.Column("seat_number", sa.Integer()))
    op.add_column("registrations", sa.Column("finish_order", sa.Integer()))
    op.add_column(
        "registrations", sa.Column("reentries", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "registrations", sa.Column("addons", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "registrations",
        sa.Column("addon_this_entry", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Checked at commit, so that the final table can redraw everyone's seats in one go.
    op.create_unique_constraint(
        "registrations_tournament_id_table_number_seat_number_key",
        "registrations",
        ["tournament_id", "table_number", "seat_number"],
        deferrable=True,
        initially="DEFERRED",
    )
    op.create_unique_constraint(
        "registrations_tournament_id_finish_order_key",
        "registrations",
        ["tournament_id", "finish_order"],
    )


def downgrade() -> None:
    op.drop_constraint("registrations_tournament_id_finish_order_key", "registrations")
    op.drop_constraint(
        "registrations_tournament_id_table_number_seat_number_key", "registrations"
    )
    for column in ["addon_this_entry", "addons", "reentries", "finish_order", "seat_number", "table_number"]:
        op.drop_column("registrations", column)
    for column in [
        "clock_remaining",
        "clock_ends_at",
        "clock_item",
        "finished_at",
        "started_at",
        "seats_per_table",
    ]:
        op.drop_column("tournaments", column)
