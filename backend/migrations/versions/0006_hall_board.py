"""The hall board: its secret link, and the chips an add-on gives for the average stack.

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("addon_stack", sa.Integer()))
    # Tournaments made before the field existed: an add-on gave as many chips as the start.
    op.execute(
        "UPDATE tournaments SET addon_stack = starting_stack WHERE addon_at_level IS NOT NULL"
    )
    op.add_column("tournaments", sa.Column("board_token", sa.String(12)))
    # Twelve random hex digits for every existing tournament, as the application makes them:
    # the first twelve of a version 4 UUID are random (PostgreSQL's random() is not secure).
    op.execute(
        "UPDATE tournaments SET board_token = left(replace(gen_random_uuid()::text, '-', ''), 12)"
    )
    op.alter_column("tournaments", "board_token", nullable=False)
    op.create_unique_constraint("tournaments_board_token_key", "tournaments", ["board_token"])


def downgrade() -> None:
    op.drop_constraint("tournaments_board_token_key", "tournaments")
    op.drop_column("tournaments", "board_token")
    op.drop_column("tournaments", "addon_stack")
