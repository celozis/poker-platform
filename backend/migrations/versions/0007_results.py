"""Tournament results: each player's place and rating points, fixed when the tournament finishes.

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-27

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("registrations", sa.Column("place", sa.Integer()))
    op.add_column("registrations", sa.Column("points", sa.Integer()))
    # Checked at commit, so that a corrected place can move the other players in one go.
    op.create_unique_constraint(
        "registrations_tournament_id_place_key",
        "registrations",
        ["tournament_id", "place"],
        deferrable=True,
        initially="DEFERRED",
    )
    # Tournaments finished before results were kept: everyone who played has a finish order,
    # the winner the last one. Points by the league's formula as app/points.py has it.
    op.execute(
        """
        WITH ranked AS (
            SELECT r.id,
                   count(*) OVER (PARTITION BY r.tournament_id) AS players,
                   count(*) OVER (PARTITION BY r.tournament_id)
                     - row_number() OVER (PARTITION BY r.tournament_id ORDER BY r.finish_order)
                     + 1 AS place
            FROM registrations r
            JOIN tournaments t ON t.id = r.tournament_id
            WHERE t.status = 'finished' AND r.finish_order IS NOT NULL
        )
        UPDATE registrations
        SET place = ranked.place,
            points = floor(10 * (sqrt(ranked.players::float8 / ranked.place) - 1) + 0.5)
        FROM ranked
        WHERE registrations.id = ranked.id
        """
    )


def downgrade() -> None:
    op.drop_constraint("registrations_tournament_id_place_key", "registrations")
    op.drop_column("registrations", "points")
    op.drop_column("registrations", "place")
