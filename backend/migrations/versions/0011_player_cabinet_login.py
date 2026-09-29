"""Players log in to their web cabinet: login codes say whom they are for, and player sessions.

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-29

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # The codes pending now were all sent to admins.
    op.add_column(
        "login_codes",
        sa.Column("purpose", sa.String(10), nullable=False, server_default="admin"),
    )
    op.alter_column("login_codes", "purpose", server_default=None)
    op.drop_constraint("login_codes_pkey", "login_codes", type_="primary")
    op.create_primary_key("login_codes_pkey", "login_codes", ["purpose", "phone"])
    op.create_table(
        "player_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "player_id",
            sa.Integer(),
            sa.ForeignKey("players.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_player_sessions_player_id", "player_sessions", ["player_id"])


def downgrade() -> None:
    op.drop_table("player_sessions")
    op.execute("DELETE FROM login_codes WHERE purpose <> 'admin'")
    op.drop_constraint("login_codes_pkey", "login_codes", type_="primary")
    op.create_primary_key("login_codes_pkey", "login_codes", ["phone"])
    op.drop_column("login_codes", "purpose")
