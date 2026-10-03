"""Club tournaments. Club-scoped like everything under /api/clubs/{club_id} (ADR-0003):
the club comes only from AdminClub, and every query filters by club.id."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, update

from app import action_log, realtime
from app.auth import CurrentAdmin, DbSession, Now
from app.clubs import AdminClub
from app.models import Club, Registration, Tournament
from app.schemas import TournamentIn, TournamentList, TournamentOut
from app.seasons import league_time_text
from app.tournament_rules import tournament_errors
from app.transactions import give_buy_ins_back, roubles, thousands

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


def _checked(tournament: TournamentIn, now: datetime) -> dict[str, Any]:
    """The tournament's fields to save, once it follows the rules. An add-on that is not offered
    gives no chips, whatever the form sent."""
    errors = tournament_errors(tournament, now)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, errors)
    fields = tournament.model_dump()
    if tournament.addon_at_level is None:
        fields["addon_stack"] = None
        fields["addon_price"] = None
    return fields


# The tournament's fields as the action log names them; the structure is only said to have changed.
_FIELD_NAMES = {
    "name": "Название",
    "starts_at": "Начало",
    "buy_in": "Бай-ин",
    "starting_stack": "Стартовый стек",
    "reentry_until_level": "Re-entry до уровня",
    "addon_at_level": "Add-on на уровне",
    "addon_stack": "Фишки add-on",
    "addon_price": "Цена add-on",
    "late_registration_until_level": "Поздняя регистрация до уровня",
    "seats_per_table": "Мест за столом",
}
_MONEY_FIELDS = ("buy_in", "addon_price")


def _shown(field: str, value: Any) -> str:
    if value is None:
        return "нет"
    if isinstance(value, datetime):
        return league_time_text(value)
    if field in _MONEY_FIELDS:
        return roubles(value)
    if isinstance(value, int):
        return thousands(value)
    return str(value)


def _changes(tournament: Tournament, fields: dict[str, Any]) -> list[str]:
    """What saving these fields changes, as the action log says it: "Бай-ин: 2 000 ₽ → 2 500 ₽"."""
    changes = []
    for field, value in fields.items():
        was = getattr(tournament, field)
        if was == value:
            continue
        if field == "structure":
            changes.append("Структура блайндов")
        else:
            changes.append(f"{_FIELD_NAMES[field]}: {_shown(field, was)} → {_shown(field, value)}")
    return changes


def _section(tournament: Tournament, now: datetime) -> str:
    """Upcoming until started (however late), live while running or paused, then past.
    A cancelled tournament never starts, so it moves to the past at its start time."""
    if tournament.status == "cancelled":
        return "upcoming" if tournament.starts_at > now else "past"
    if tournament.status == "scheduled":
        return "upcoming"
    return "live" if tournament.is_live else "past"


@router.get("")
def list_tournaments(club: AdminClub, session: DbSession, now: Now) -> TournamentList:
    tournaments = session.scalars(
        select(Tournament).where(Tournament.club_id == club.id).order_by(Tournament.starts_at)
    ).all()
    return TournamentList(
        live=[TournamentOut.model_validate(t) for t in tournaments if _section(t, now) == "live"],
        upcoming=[TournamentOut.model_validate(t) for t in tournaments if _section(t, now) == "upcoming"],
        past=[TournamentOut.model_validate(t) for t in reversed(tournaments) if _section(t, now) == "past"],
    )


@router.post("", status_code=status.HTTP_201_CREATED)
def create_tournament(
    body: TournamentIn, club: AdminClub, session: DbSession, now: Now
) -> TournamentOut:
    tournament = Tournament(club_id=club.id, status="scheduled", **_checked(body, now))
    session.add(tournament)
    session.commit()
    return TournamentOut.model_validate(tournament)


@router.put("/{tournament_id}")
def update_tournament(
    tournament_id: int,
    body: TournamentIn,
    club: AdminClub,
    admin: CurrentAdmin,
    session: DbSession,
    now: Now,
) -> TournamentOut:
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    if tournament.has_started:
        raise HTTPException(status.HTTP_409_CONFLICT, "Турнир уже начался, его нельзя изменить")
    if tournament.status == "cancelled":
        raise HTTPException(status.HTTP_409_CONFLICT, "Турнир отменён, его нельзя изменить")
    starts_at = tournament.starts_at
    fields = _checked(body, now)
    changes = _changes(tournament, fields)
    if changes:
        action_log.record(session, tournament, admin, "tournament_edited", now, details="; ".join(changes))
    for field, value in fields.items():
        setattr(tournament, field, value)
    if tournament.starts_at != starts_at:
        # The players are reminded again, of the new time (app/bot/notifications.py).
        session.execute(
            update(Registration)
            .where(Registration.tournament_id == tournament.id)
            .values(reminded_at=None)
        )
    realtime.tournament_changed(session, tournament.id)
    session.commit()
    return TournamentOut.model_validate(tournament)


@router.post("/{tournament_id}/cancel")
def cancel_tournament(
    tournament_id: int, club: AdminClub, admin: CurrentAdmin, session: DbSession, now: Now
) -> TournamentOut:
    """Cancels a tournament that has not started; the buy-ins of those who came are given back."""
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    if tournament.has_started:
        raise HTTPException(status.HTTP_409_CONFLICT, "Турнир уже начался, его нельзя отменить")
    tournament.status = "cancelled"
    refunded = give_buy_ins_back(session, tournament, admin, now)
    action_log.record(
        session,
        tournament,
        admin,
        "tournament_cancelled",
        now,
        details=action_log.given_back(refunded),
    )
    realtime.tournament_changed(session, tournament.id)
    session.commit()
    return TournamentOut.model_validate(tournament)
