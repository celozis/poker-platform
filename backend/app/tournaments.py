"""Club tournaments. Club-scoped like everything under /api/clubs/{club_id} (ADR-0003):
the club comes only from AdminClub, and every query filters by club.id."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.auth import DbSession, Now
from app.clubs import AdminClub
from app.models import Club, Tournament
from app.schemas import TournamentIn, TournamentList, TournamentOut
from app.tournament_rules import tournament_errors

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments")


def club_tournament(
    session: DbSession, club: Club, tournament_id: int, *, for_update: bool = False
) -> Tournament:
    """The club's own tournament, or 404. Changes lock it (`for_update`), so that two parallel
    changes cannot both pass the checks made before them."""
    statement = select(Tournament).where(
        Tournament.id == tournament_id, Tournament.club_id == club.id
    )
    tournament = session.scalar(statement.with_for_update() if for_update else statement)
    if tournament is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Турнир не найден")
    return tournament


def _check_rules(tournament: TournamentIn, now: datetime) -> None:
    errors = tournament_errors(tournament, now)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, errors)


@router.get("")
def list_tournaments(club: AdminClub, session: DbSession, now: Now) -> TournamentList:
    tournaments = session.scalars(
        select(Tournament).where(Tournament.club_id == club.id).order_by(Tournament.starts_at)
    ).all()
    return TournamentList(
        upcoming=[TournamentOut.model_validate(t) for t in tournaments if not t.has_started(now)],
        past=[TournamentOut.model_validate(t) for t in reversed(tournaments) if t.has_started(now)],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tournament(
    body: TournamentIn, club: AdminClub, session: DbSession, now: Now
) -> TournamentOut:
    _check_rules(body, now)
    tournament = Tournament(club_id=club.id, status="scheduled", **body.model_dump())
    session.add(tournament)
    session.commit()
    return TournamentOut.model_validate(tournament)


@router.put("/{tournament_id}")
def update_tournament(
    tournament_id: int, body: TournamentIn, club: AdminClub, session: DbSession, now: Now
) -> TournamentOut:
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    if tournament.has_started(now):
        raise HTTPException(status.HTTP_409_CONFLICT, "Турнир уже начался, его нельзя изменить")
    if tournament.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Турнир отменён, его нельзя изменить")
    _check_rules(body, now)
    for field, value in body.model_dump().items():
        setattr(tournament, field, value)
    session.commit()
    return TournamentOut.model_validate(tournament)


@router.post("/{tournament_id}/cancel")
def cancel_tournament(
    tournament_id: int, club: AdminClub, session: DbSession, now: Now
) -> TournamentOut:
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    if tournament.has_started(now):
        raise HTTPException(status.HTTP_409_CONFLICT, "Турнир уже начался, его нельзя отменить")
    tournament.status = "cancelled"
    session.commit()
    return TournamentOut.model_validate(tournament)
