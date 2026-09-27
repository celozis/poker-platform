"""The club rating: the points each player has scored in the club's finished tournaments of
a season (app/seasons.py), added up. Worked out afresh on every request, so a corrected place
(app/results.py) is in it at once.

Club-scoped like everything under /api/clubs/{club_id} (ADR-0003): only the club's own
tournaments count, even for a player who also plays elsewhere in the league."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import DbSession, Now
from app.clubs import AdminClub
from app.models import Player, Registration, Tournament
from app.schemas import ClubRating, PlayerOut, RatingRow, SeasonOut
from app.seasons import next_season, previous_season, season_at, season_by_id

router = APIRouter(prefix="/api/clubs/{club_id}/rating")


def club_standings(
    session: Session, club_id: int, starts_at: datetime, ends_at: datetime
) -> list[RatingRow]:
    """The club's players by the points of its finished tournaments that start in
    [starts_at, ends_at), the most first; equal points share a position, and the next position
    counts everyone above. A season's rating, or any other period's."""
    totals = (
        select(
            Registration.player_id,
            func.sum(Registration.points).label("points"),
            func.count().label("tournaments"),
        )
        .join(Tournament, Tournament.id == Registration.tournament_id)
        .where(
            Tournament.club_id == club_id,
            Tournament.status == "finished",
            Tournament.starts_at >= starts_at,
            Tournament.starts_at < ends_at,
            Registration.place.is_not(None),
        )
        .group_by(Registration.player_id)
        .subquery()
    )
    rows = session.execute(
        select(Player, totals.c.points, totals.c.tournaments)
        .join(totals, totals.c.player_id == Player.id)
        .order_by(totals.c.points.desc(), Player.name, Player.id)
    ).all()
    standings: list[RatingRow] = []
    for number, (player, points, tournaments) in enumerate(rows, start=1):
        tied = standings and standings[-1].points == points
        standings.append(
            RatingRow(
                position=standings[-1].position if tied else number,
                player=PlayerOut.model_validate(player),
                points=points,
                tournaments=tournaments,
            )
        )
    return standings


@router.get("")
def club_rating(
    club: AdminClub, session: DbSession, now: Now, season: str | None = None
) -> ClubRating:
    """The rating of the current season, or of an earlier one by its id ("2026-1"), so that
    the standings of a season just over can still be seen."""
    current = season_at(now)
    shown = current if season is None else season_by_id(season)
    if shown is None or shown.starts_at > current.starts_at:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого сезона нет")
    return ClubRating(
        season=SeasonOut.model_validate(shown),
        previous_season=previous_season(shown).id,
        next_season=None if shown == current else next_season(shown).id,
        players=club_standings(session, club.id, shown.starts_at, shown.ends_at),
    )
