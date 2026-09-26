"""Players registered for a club tournament, and their check-in on the day.

Club-scoped like everything under /api/clubs/{club_id} (ADR-0003): the tournament and the player
are looked up only among the club's own."""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import contains_eager

from app.auth import DbSession, Now
from app.clubs import AdminClub
from app.models import Club, ClubPlayer, Player, Registration, Tournament
from app.schemas import RegistrationIn, RegistrationOut, TournamentRegistrations
from app.tournaments import club_tournament

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments/{tournament_id}/registrations")

# Check-in is open on the tournament's day: from this long before the start to this long after it,
# so latecomers can still be checked in. Clubs have no time zone yet, hence no calendar day.
CHECK_IN_HOURS = 12
CHECK_IN_WINDOW = timedelta(hours=CHECK_IN_HOURS)


def _registration_closed_because(tournament: Tournament, now: datetime) -> str | None:
    """Players sign up for an upcoming tournament; late registration is not supported yet."""
    if tournament.status == "cancelled":
        return "Турнир отменён, регистрация закрыта"
    if tournament.has_started(now):
        return "Турнир уже начался, регистрация закрыта"
    return None


def _check_in_closed_because(tournament: Tournament, now: datetime) -> str | None:
    if tournament.status == "cancelled":
        return "Турнир отменён"
    if now < tournament.starts_at - CHECK_IN_WINDOW:
        return f"Отметка о приходе откроется за {CHECK_IN_HOURS} часов до начала турнира"
    if now > tournament.starts_at + CHECK_IN_WINDOW:
        return f"Отметка о приходе закрыта: турнир начался больше {CHECK_IN_HOURS} часов назад"
    return None


def _club_player(session: DbSession, club: Club, player_id: int) -> Player:
    player = session.scalar(
        select(Player)
        .join(ClubPlayer, ClubPlayer.player_id == Player.id)
        .where(Player.id == player_id, ClubPlayer.club_id == club.id)
    )
    if player is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Игрок не найден в клубе")
    return player


def _registration(session: DbSession, tournament_id: int, player_id: int) -> Registration | None:
    return session.scalar(
        select(Registration).where(
            Registration.tournament_id == tournament_id, Registration.player_id == player_id
        )
    )


@router.get("")
def list_registrations(
    tournament_id: int, club: AdminClub, session: DbSession, now: Now
) -> TournamentRegistrations:
    tournament = club_tournament(session, club, tournament_id)
    registrations = session.scalars(
        select(Registration)
        .join(Registration.player)
        .options(contains_eager(Registration.player))
        .where(Registration.tournament_id == tournament.id)
        .order_by(Player.name, Player.id)
    ).all()
    return TournamentRegistrations(
        registration_open=_registration_closed_because(tournament, now) is None,
        check_in_open=_check_in_closed_because(tournament, now) is None,
        registrations=[RegistrationOut.model_validate(r) for r in registrations]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def register_player(
    tournament_id: int, body: RegistrationIn, club: AdminClub, session: DbSession, now: Now
) -> RegistrationOut:
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    closed = _registration_closed_because(tournament, now)
    if closed:
        raise HTTPException(status.HTTP_409_CONFLICT, closed)
    player = _club_player(session, club, body.player_id)
    # The tournament row is locked, so a parallel registration of the same player waits here.
    if _registration(session, tournament.id, player.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{player.name} уже зарегистрирован на этот турнир"
        )
    registration = Registration(
        club_id=club.id, tournament_id=tournament.id, player_id=player.id, registered_at=now
    )
    session.add(registration)
    session.commit()
    return RegistrationOut.model_validate(registration)


def _registered(session: DbSession, tournament: Tournament, player_id: int) -> Registration:
    registration = _registration(session, tournament.id, player_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Игрок не зарегистрирован на этот турнир")
    return registration


@router.delete("/{player_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_registration(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now
) -> None:
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    closed = _registration_closed_because(tournament, now)
    if closed:
        raise HTTPException(status.HTTP_409_CONFLICT, closed)
    session.delete(_registered(session, tournament, player_id))
    session.commit()


def _set_checked_in(
    tournament_id: int, player_id: int, club: Club, session: DbSession, now: Now, checked_in: bool
) -> RegistrationOut:
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    closed = _check_in_closed_because(tournament, now)
    if closed:
        raise HTTPException(status.HTTP_409_CONFLICT, closed)
    registration = _registered(session, tournament, player_id)
    if checked_in and registration.checked_in_at is None:
        registration.checked_in_at = now
    if not checked_in:
        registration.checked_in_at = None
    session.commit()
    return RegistrationOut.model_validate(registration)


@router.post("/{player_id}/check-in")
def check_in(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now
) -> RegistrationOut:
    return _set_checked_in(tournament_id, player_id, club, session, now, checked_in=True)


@router.delete("/{player_id}/check-in")
def undo_check_in(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now
) -> RegistrationOut:
    return _set_checked_in(tournament_id, player_id, club, session, now, checked_in=False)
