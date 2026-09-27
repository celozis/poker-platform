"""A finished tournament's results: every player's place and rating points, and the admin's
correction of a place entered by mistake.

Places are fixed when the tournament finishes (app/game.py calls `rank`); until then they are
worked out from the order of knock-outs. Club-scoped like everything under /api/clubs/{club_id}
(ADR-0003)."""

from typing import cast

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import contains_eager

from app.auth import DbSession
from app.clubs import AdminClub
from app.models import Registration, Tournament
from app.points import points
from app.schemas import PlaceIn, ResultOut, TournamentResults, TournamentStatus
from app.tournaments import club_tournament

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments/{tournament_id}/results")


def rank(in_order: list[Registration]) -> None:
    """Gives the players their places in this order, the winner first, and the points for them."""
    for place, registration in enumerate(in_order, start=1):
        registration.place = place
        registration.points = points(place, len(in_order))


def _results(session: DbSession, tournament: Tournament) -> list[Registration]:
    return list(
        session.scalars(
            select(Registration)
            .join(Registration.player)
            .options(contains_eager(Registration.player))
            .where(Registration.tournament_id == tournament.id, Registration.place.is_not(None))
            .order_by(Registration.place)
        ).all()
    )


def _tournament_results(tournament: Tournament, results: list[Registration]) -> TournamentResults:
    return TournamentResults(
        status=cast(TournamentStatus, tournament.status),
        results=[ResultOut.model_validate(r) for r in results],
    )


@router.get("")
def get_results(tournament_id: int, club: AdminClub, session: DbSession) -> TournamentResults:
    tournament = club_tournament(session, club, tournament_id)
    return _tournament_results(tournament, _results(session, tournament))


@router.put("/{player_id}")
def correct_place(
    tournament_id: int, player_id: int, body: PlaceIn, club: AdminClub, session: DbSession
) -> TournamentResults:
    """Puts the player on the place they really finished in: those between the old place and the
    new one move up or down by one, as if that one knock-out had been marked at the right time.
    Everyone's points are counted again, and so is the club rating, which adds them up."""
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    if tournament.status != "finished":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Места исправляют после завершения турнира; пока он идёт, отмените выбывание",
        )
    results = _results(session, tournament)
    registration = next((r for r in results if r.player_id == player_id), None)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Игрок не играл в этом турнире")
    if not 1 <= body.place <= len(results):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, [f"Место: от 1 до {len(results)}"]
        )
    results.remove(registration)
    results.insert(body.place - 1, registration)
    rank(results)
    session.commit()
    return _tournament_results(tournament, results)
