"""League players, each club's own list of them, and tournament registrations.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "players",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("phone", sa.String(16), nullable=False, unique=True),
        sa.Column("consent_given_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "club_players",
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), primary_key=True),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), primary_key=True),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_club_players_player_id", "club_players", ["player_id"])
    op.create_table(
        "registrations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("club_id", sa.Integer(), sa.ForeignKey("clubs.id"), nullable=False),
        sa.Column("tournament_id", sa.Integer(), sa.ForeignKey("tournaments.id"), nullable=False),
        sa.Column("player_id", sa.Integer(), sa.ForeignKey("players.id"), nullable=False),
        sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("checked_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tournament_id", "player_id", name="registrations_tournament_id_player_id_key"
        ),
    )
    op.create_index("ix_registrations_club_id", "registrations", ["club_id"])
    op.create_index("ix_registrations_tournament_id", "registrations", ["tournament_id"])
    op.create_index("ix_registrations_player_id", "registrations", ["player_id"])


def downgrade() -> None:
    op.drop_table("registrations")
    op.drop_table("club_players")
    op.drop_table("players")
