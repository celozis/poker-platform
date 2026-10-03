"""Players registered for a club tournament, and their check-in on the day. Once the tournament
is running, players are seated and knocked out in app/game.py. Every change is told to the
tournament's watchers (app/realtime.py), such as the admin panel open on another screen.

Club-scoped like everything under /api/clubs/{club_id} (ADR-0003): the tournament and the player
are looked up only among the club's own."""

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager

from app import action_log, realtime
from app.auth import CurrentAdmin, DbSession, Now
from app.clubs import AdminClub
from app.game import late_registration_closed_because
from app.models import Club, ClubPlayer, Player, Registration, Tournament
from app.schemas import (
    CheckInUndone,
    PaymentIn,
    Refund,
    RegistrationIn,
    RegistrationOut,
    TournamentRegistrations,
)
from app.tournaments import club_tournament
from app.transactions import give_buy_ins_back, take_payment

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments/{tournament_id}/registrations")

# Check-in is open on the tournament's day: from this long before the start to this long after it,
# so latecomers can still be checked in. Clubs have no time zone yet, hence no calendar day.
CHECK_IN_HOURS = 12
CHECK_IN_WINDOW = timedelta(hours=CHECK_IN_HOURS)


def registration_closed_because(tournament: Tournament, now: datetime) -> str | None:
    """Players sign up until the tournament is started, however late that is, and afterwards
    while its late registration is open."""
    if tournament.status == "cancelled":
        return "Турнир отменён, регистрация закрыта"
    if tournament.status == "finished":
        return "Турнир завершён, регистрация закрыта"
    if tournament.is_live:
        return late_registration_closed_because(tournament, now)
    return None


def dropping_out_closed_because(tournament: Tournament) -> str | None:
    if tournament.status == "cancelled":
        return "Турнир отменён, регистрация закрыта"
    if tournament.has_started:
        return "Турнир уже начался, снять с регистрации нельзя"
    return None


def _check_in_closed_because(tournament: Tournament, now: datetime) -> str | None:
    if tournament.status == "cancelled":
        return "Турнир отменён"
    if tournament.has_started:
        return "Турнир уже начался: опоздавшего сажают через позднюю регистрацию"
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


def find_registration(
    session: Session, tournament_id: int, player_id: int
) -> Registration | None:
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
        registration_open=registration_closed_because(tournament, now) is None,
        drop_out_open=dropping_out_closed_because(tournament) is None,
        check_in_open=_check_in_closed_because(tournament, now) is None,
        registrations=[RegistrationOut.model_validate(r) for r in registrations]
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def register_player(
    tournament_id: int,
    body: RegistrationIn,
    club: AdminClub,
    admin: CurrentAdmin,
    session: DbSession,
    now: Now,
) -> RegistrationOut:
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    closed = registration_closed_because(tournament, now)
    if closed:
        raise HTTPException(status.HTTP_409_CONFLICT, closed)
    player = _club_player(session, club, body.player_id)
    # The tournament row is locked, so a parallel registration of the same player waits here.
    if find_registration(session, tournament.id, player.id) is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"{player.name} уже зарегистрирован на этот турнир"
        )
    registration = Registration(
        club_id=club.id, tournament_id=tournament.id, player_id=player.id, registered_at=now
    )
    session.add(registration)
    action_log.record(session, tournament, admin, "registered", now, player_id=player.id)
    realtime.tournament_changed(session, tournament.id)
    session.commit()
    return RegistrationOut.model_validate(registration)


def _registered(session: DbSession, tournament: Tournament, player_id: int) -> Registration:
    registration = find_registration(session, tournament.id, player_id)
    if registration is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Игрок не зарегистрирован на этот турнир")
    return registration


@router.delete("/{player_id}")
def cancel_registration(
    tournament_id: int,
    player_id: int,
    club: AdminClub,
    admin: CurrentAdmin,
    session: DbSession,
    now: Now,
) -> Refund:
    """Takes the player off the tournament before the start, giving back a buy-in they paid."""
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    closed = dropping_out_closed_because(tournament)
    if closed:
        raise HTTPException(status.HTTP_409_CONFLICT, closed)
    session.delete(_registered(session, tournament, player_id))
    refunded = give_buy_ins_back(session, tournament, admin, now, player_id)
    action_log.record(
        session,
        tournament,
        admin,
        "registration_cancelled",
        now,
        player_id=player_id,
        details=action_log.given_back(refunded),
    )
    realtime.tournament_changed(session, tournament.id)
    session.commit()
    return Refund(refunded=refunded)


def _check_in_open(
    session: DbSession, club: Club, tournament_id: int, player_id: int, now: datetime
) -> tuple[Tournament, Registration]:
    """The tournament, locked for a change, and the player's registration, while check-in is
    open."""
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    closed = _check_in_closed_because(tournament, now)
    if closed:
        raise HTTPException(status.HTTP_409_CONFLICT, closed)
    return tournament, _registered(session, tournament, player_id)


@router.post("/{player_id}/check-in")
def check_in(
    tournament_id: int,
    player_id: int,
    club: AdminClub,
    admin: CurrentAdmin,
    session: DbSession,
    now: Now,
    payment: PaymentIn | None = None,
) -> RegistrationOut:
    """Marks the player as come to the club; they pay the buy-in then."""
    tournament, registration = _check_in_open(session, club, tournament_id, player_id, now)
    if registration.checked_in_at is None:
        paid = take_payment(session, tournament, player_id, "buy_in", payment, admin, now)
        registration.checked_in_at = now
        action_log.record(
            session,
            tournament,
            admin,
            "checked_in",
            now,
            player_id=player_id,
            details=action_log.paid(paid),
        )
    realtime.tournament_changed(session, tournament.id)
    session.commit()
    return RegistrationOut.model_validate(registration)


@router.delete("/{player_id}/check-in")
def undo_check_in(
    tournament_id: int,
    player_id: int,
    club: AdminClub,
    admin: CurrentAdmin,
    session: DbSession,
    now: Now,
) -> CheckInUndone:
    """Takes a mistaken check-in back, and the buy-in with it: the answer says how much to give
    back to the player."""
    tournament, registration = _check_in_open(session, club, tournament_id, player_id, now)
    refunded = 0
    if registration.checked_in_at is not None:
        refunded = give_buy_ins_back(session, tournament, admin, now, player_id)
        registration.checked_in_at = None
        action_log.record(
            session,
            tournament,
            admin,
            "check_in_undone",
            now,
            player_id=player_id,
            details=action_log.given_back(refunded),
        )
    realtime.tournament_changed(session, tournament.id)
    session.commit()
    return CheckInUndone(
        **RegistrationOut.model_validate(registration).model_dump(), refunded=refunded
    )
