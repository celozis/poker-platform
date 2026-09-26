"""Running a club tournament from the start to the final table: the seating, the blind clock,
knock-outs, re-entries, add-ons, late registration and moves that keep tables even.

Club-scoped like everything under /api/clubs/{club_id} (ADR-0003). Every change locks the
tournament row, so parallel changes to one game are made one after another. Every action answers
with the whole game (GameState), so the admin panel just shows what it gets.

The rules themselves live in pure modules: app/seating.py, app/blind_clock.py and
app/entry_windows.py."""

from dataclasses import asdict
from datetime import datetime, timedelta
from math import ceil
from random import Random
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.orm import contains_eager

from app.auth import DbSession, Now
from app.blind_clock import BlindClock
from app.clubs import AdminClub
from app.entry_windows import EntryWindows, entry_windows
from app.models import Club, Player, Registration, Tournament
from app.schemas import (
    ClockOut,
    EntryWindowsOut,
    FinishedPlayer,
    GameState,
    MoveIn,
    MoveOut,
    PlayerOut,
    RegistrationOut,
    SeatedPlayer,
    StructureItem,
    TournamentStatus,
)
from app.seating import (
    Seat,
    Seating,
    final_table_seating,
    initial_seating,
    seat_for_newcomer,
    suggested_move,
)
from app.tournaments import club_tournament

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments/{tournament_id}")


def get_random() -> Random:
    return Random()


Rng = Annotated[Random, Depends(get_random)]

_STRUCTURE = TypeAdapter(list[StructureItem])


def _structure(tournament: Tournament) -> list[StructureItem]:
    return _STRUCTURE.validate_python(tournament.structure)


def _durations(tournament: Tournament) -> list[timedelta]:
    return [timedelta(minutes=item.duration_minutes) for item in _structure(tournament)]


def _clock(tournament: Tournament) -> BlindClock | None:
    if tournament.clock_item is None:
        return None
    return BlindClock(
        _durations(tournament),
        tournament.clock_item,
        ends_at=tournament.clock_ends_at,
        remaining=tournament.clock_remaining,
    )


def _set_clock(tournament: Tournament, clock: BlindClock) -> None:
    tournament.clock_item = clock.item
    tournament.clock_ends_at = clock.ends_at
    tournament.clock_remaining = clock.remaining


def _registrations(session: DbSession, tournament: Tournament) -> list[Registration]:
    return list(
        session.scalars(
            select(Registration)
            .join(Registration.player)
            .options(contains_eager(Registration.player))
            .where(Registration.tournament_id == tournament.id)
            .order_by(Player.name, Player.id)
        ).all()
    )


def _seating(registrations: list[Registration]) -> Seating:
    return {
        r.player_id: Seat(r.table_number, r.seat_number)
        for r in registrations
        if r.table_number is not None and r.seat_number is not None
    }


def _places(registrations: list[Registration]) -> dict[int, int]:
    """Place by player for those who have finished. Whoever finishes later places higher, so a
    player's place is the number of players in the tournament minus those who finished before
    them. A re-entry or a late registration after a knock-out moves that player's place down."""
    played = [r for r in registrations if r.table_number is not None or r.finish_order is not None]
    finished = sorted(
        (r for r in played if r.finish_order is not None), key=lambda r: r.finish_order or 0
    )
    return {r.player_id: len(played) - before for before, r in enumerate(finished)}


def current_windows(tournament: Tournament, now: datetime) -> EntryWindows:
    """What the tournament takes right now; nothing unless it is running or paused."""
    clock = _clock(tournament)
    if clock is None or not tournament.is_live:
        return EntryWindows(reentry=False, addon=False, late_registration=False)
    return entry_windows(
        _structure(tournament),
        clock.at(now).item,
        reentry_until_level=tournament.reentry_until_level,
        addon_at_level=tournament.addon_at_level,
        late_registration_until_level=tournament.late_registration_until_level,
    )


def late_registration_closed_because(tournament: Tournament, now: datetime) -> str | None:
    """Why a running or paused tournament takes no more players right now, if it does not."""
    until = tournament.late_registration_until_level
    if until is None:
        return "Турнир уже идёт, поздней регистрации в нём нет"
    if not current_windows(tournament, now).late_registration:
        return f"Поздняя регистрация закрыта: она шла до уровня {until}"
    return None


def _state(session: DbSession, tournament: Tournament, now: datetime) -> GameState:
    registrations = _registrations(session, tournament)
    by_player = {r.player_id: r for r in registrations}
    clock = _clock(tournament)
    clock_out = None
    if clock is not None:
        clock = clock.at(now)
        clock_out = ClockOut(
            running=clock.running,
            item=clock.item,
            seconds_left=ceil(clock.time_left(now).total_seconds()),
        )
    windows = current_windows(tournament, now)
    seating = _seating(registrations)
    places = _places(registrations)
    move = suggested_move(seating, tournament.seats_per_table) if tournament.is_live else None
    return GameState(
        status=cast(TournamentStatus, tournament.status),
        seats_per_table=tournament.seats_per_table,
        clock=clock_out,
        windows=EntryWindowsOut(**asdict(windows)),
        in_game=[
            SeatedPlayer(
                player=PlayerOut.model_validate(by_player[player_id].player),
                table=seat.table,
                seat=seat.seat,
                reentries=by_player[player_id].reentries,
                addons=by_player[player_id].addons,
                addon_this_entry=by_player[player_id].addon_this_entry,
            )
            for player_id, seat in sorted(seating.items(), key=lambda item: item[1])
        ],
        out=[
            FinishedPlayer(
                player=PlayerOut.model_validate(by_player[player_id].player),
                place=place,
                reentries=by_player[player_id].reentries,
                addons=by_player[player_id].addons,
            )
            for player_id, place in sorted(places.items(), key=lambda item: item[1])
        ],
        waiting=[
            RegistrationOut.model_validate(r)
            for r in registrations
            if r.status in ("registered", "checked_in")
        ],
        suggested_move=None
        if move is None
        else MoveOut(
            player=PlayerOut.model_validate(by_player[move.player_id].player),
            from_table=move.from_seat.table,
            from_seat=move.from_seat.seat,
            to_table=move.to_seat.table,
            to_seat=move.to_seat.seat,
        ),
    )


def _refuse(message: str) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, message)


@router.get("/game")
def get_game(tournament_id: int, club: AdminClub, session: DbSession, now: Now) -> GameState:
    return _state(session, club_tournament(session, club, tournament_id), now)


@router.post("/start")
def start(
    tournament_id: int, club: AdminClub, session: DbSession, now: Now, rng: Rng
) -> GameState:
    """Seats everyone who has come and starts the blind clock on the first level."""
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    if tournament.status == "finished":
        raise _refuse("Турнир уже завершён, его нельзя снова запустить")
    if tournament.is_live:
        raise _refuse("Турнир уже идёт")
    if tournament.status == "cancelled":
        raise _refuse("Турнир отменён")
    arrived = {r.player_id: r for r in _registrations(session, tournament) if r.checked_in_at}
    if len(arrived) < 2:
        raise _refuse("Для старта нужны хотя бы два пришедших игрока")
    for player_id, seat in initial_seating(list(arrived), tournament.seats_per_table, rng).items():
        arrived[player_id].table_number, arrived[player_id].seat_number = seat.table, seat.seat
    tournament.status = "running"
    tournament.started_at = now
    _set_clock(tournament, BlindClock.started(_durations(tournament), now))
    session.commit()
    return _state(session, tournament, now)


def _live_tournament(session: DbSession, club: Club, tournament_id: int) -> Tournament:
    """The club's tournament, locked for a change, but only while it is running or paused."""
    tournament = club_tournament(session, club, tournament_id, for_update=True)
    if tournament.status in ("scheduled", "cancelled"):
        raise _refuse("Турнир ещё не начался" if tournament.status == "scheduled" else "Турнир отменён")
    if tournament.status == "finished":
        raise _refuse("Турнир завершён")
    return tournament


def _live_clock(tournament: Tournament) -> BlindClock:
    clock = _clock(tournament)
    assert clock is not None, "a started tournament has a clock"
    return clock


@router.post("/pause")
def pause(tournament_id: int, club: AdminClub, session: DbSession, now: Now) -> GameState:
    tournament = _live_tournament(session, club, tournament_id)
    if tournament.status == "paused":
        raise _refuse("Турнир уже на паузе")
    _set_clock(tournament, _live_clock(tournament).paused(now))
    tournament.status = "paused"
    session.commit()
    return _state(session, tournament, now)


@router.post("/resume")
def resume(tournament_id: int, club: AdminClub, session: DbSession, now: Now) -> GameState:
    tournament = _live_tournament(session, club, tournament_id)
    if tournament.status != "paused":
        raise _refuse("Турнир не на паузе")
    _set_clock(tournament, _live_clock(tournament).resumed(now))
    tournament.status = "running"
    session.commit()
    return _state(session, tournament, now)


def _switch_level(
    tournament_id: int, club: Club, session: DbSession, now: datetime, step: int
) -> GameState:
    tournament = _live_tournament(session, club, tournament_id)
    clock = _live_clock(tournament)
    if not clock.can_move(step, now):
        raise _refuse("Это последний уровень структуры" if step > 0 else "Это первый уровень структуры")
    _set_clock(tournament, clock.moved(step, now))
    session.commit()
    return _state(session, tournament, now)


@router.post("/next-level")
def next_level(tournament_id: int, club: AdminClub, session: DbSession, now: Now) -> GameState:
    """Moves on to the next item of the structure, a level or a break, from its start."""
    return _switch_level(tournament_id, club, session, now, step=1)


@router.post("/previous-level")
def previous_level(
    tournament_id: int, club: AdminClub, session: DbSession, now: Now
) -> GameState:
    return _switch_level(tournament_id, club, session, now, step=-1)


def _registered(registrations: list[Registration], player_id: int) -> Registration:
    for registration in registrations:
        if registration.player_id == player_id:
            return registration
    raise HTTPException(status.HTTP_404_NOT_FOUND, "Игрок не зарегистрирован на этот турнир")


def _require_in_game(registration: Registration) -> None:
    if registration.status == "out":
        raise _refuse(f"Игрок {registration.player.name} уже выбыл")
    if registration.status != "in_game":
        raise _refuse(f"Игрок {registration.player.name} не в игре")


def _require_out(registration: Registration) -> None:
    if registration.status != "out":
        still = "ещё в игре" if registration.status == "in_game" else "не в игре"
        raise _refuse(f"Игрок {registration.player.name} {still}")


def _sit(registration: Registration, seat: Seat | None) -> None:
    registration.table_number = None if seat is None else seat.table
    registration.seat_number = None if seat is None else seat.seat


def _finish(registration: Registration, registrations: list[Registration]) -> None:
    """Takes the player out of the game as the next to finish."""
    registration.finish_order = 1 + max((r.finish_order or 0 for r in registrations), default=0)
    _sit(registration, None)


@router.post("/players/{player_id}/knock-out")
def knock_out(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now, rng: Rng
) -> GameState:
    """Knocks the player out. The last player standing wins and the tournament is finished;
    once the players left fit at one table, they are drawn for the final table."""
    tournament = _live_tournament(session, club, tournament_id)
    registrations = _registrations(session, tournament)
    registration = _registered(registrations, player_id)
    _require_in_game(registration)
    _finish(registration, registrations)
    left = [r for r in registrations if r.status == "in_game"]
    if len(left) == 1:
        _finish(left[0], registrations)
        clock = _live_clock(tournament)
        _set_clock(tournament, clock.paused(now) if clock.running else clock)
        tournament.status = "finished"
        tournament.finished_at = now
    else:
        final = final_table_seating(_seating(registrations), tournament.seats_per_table, rng)
        if final is not None:
            for r in left:
                _sit(r, final[r.player_id])
    session.commit()
    return _state(session, tournament, now)


@router.post("/players/{player_id}/undo-knock-out")
def undo_knock_out(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now, rng: Rng
) -> GameState:
    """Takes back a knock-out marked by mistake: the player returns to the table with the fewest
    players, and it does not count as a re-entry. Only while the tournament is live; places in a
    finished tournament are corrected with the results."""
    tournament = _live_tournament(session, club, tournament_id)
    registrations = _registrations(session, tournament)
    registration = _registered(registrations, player_id)
    _require_out(registration)
    registration.finish_order = None
    _sit(registration, seat_for_newcomer(_seating(registrations), tournament.seats_per_table, rng))
    session.commit()
    return _state(session, tournament, now)


@router.post("/players/{player_id}/reentry")
def reentry(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now, rng: Rng
) -> GameState:
    """Takes a knocked-out player back into the game at the table with the fewest players."""
    tournament = _live_tournament(session, club, tournament_id)
    registrations = _registrations(session, tournament)
    registration = _registered(registrations, player_id)
    _require_out(registration)
    if tournament.reentry_until_level is None:
        raise _refuse("В этом турнире нет re-entry")
    if not current_windows(tournament, now).reentry:
        raise _refuse(f"Re-entry закрыт: он был до уровня {tournament.reentry_until_level}")
    registration.finish_order = None
    registration.reentries += 1
    registration.addon_this_entry = False
    _sit(registration, seat_for_newcomer(_seating(registrations), tournament.seats_per_table, rng))
    session.commit()
    return _state(session, tournament, now)


@router.post("/players/{player_id}/addon")
def addon(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now
) -> GameState:
    """One add-on per entry: a player who re-entered can take it again."""
    tournament = _live_tournament(session, club, tournament_id)
    registration = _registered(_registrations(session, tournament), player_id)
    _require_in_game(registration)
    if tournament.addon_at_level is None:
        raise _refuse("В этом турнире нет add-on")
    if not current_windows(tournament, now).addon:
        raise _refuse(f"Add-on берут на уровне {tournament.addon_at_level} и в перерыве после него")
    if registration.addon_this_entry:
        raise _refuse(f"Игрок {registration.player.name} уже взял add-on")
    registration.addons += 1
    registration.addon_this_entry = True
    session.commit()
    return _state(session, tournament, now)


@router.post("/players/{player_id}/seat")
def seat_late_player(
    tournament_id: int, player_id: int, club: AdminClub, session: DbSession, now: Now, rng: Rng
) -> GameState:
    """Seats a registered player who was not there at the start, while late registration is
    open; this also checks them in."""
    tournament = _live_tournament(session, club, tournament_id)
    registrations = _registrations(session, tournament)
    registration = _registered(registrations, player_id)
    if registration.status in ("in_game", "out"):
        already = "уже в игре" if registration.status == "in_game" else "уже выбыл"
        raise _refuse(f"Игрок {registration.player.name} {already}")
    closed = late_registration_closed_because(tournament, now)
    if closed:
        raise _refuse(closed)
    registration.checked_in_at = registration.checked_in_at or now
    _sit(registration, seat_for_newcomer(_seating(registrations), tournament.seats_per_table, rng))
    session.commit()
    return _state(session, tournament, now)


@router.post("/players/{player_id}/move")
def move_player(
    tournament_id: int, player_id: int, body: MoveIn, club: AdminClub, session: DbSession, now: Now
) -> GameState:
    """Moves a player to a free seat: the suggested move, or any other the floor decides on."""
    tournament = _live_tournament(session, club, tournament_id)
    registrations = _registrations(session, tournament)
    registration = _registered(registrations, player_id)
    _require_in_game(registration)
    seating = _seating(registrations)
    # A table in play, or the next number to open a new one.
    tables = sorted({seat.table for seat in seating.values()})
    new_table = tables[-1] + 1
    if body.table not in (*tables, new_table):
        in_play = ", ".join(map(str, tables))
        raise _refuse(
            f"Стола {body.table} нет: пересадить можно за стол {in_play} или открыть стол {new_table}"
        )
    if not 1 <= body.seat <= tournament.seats_per_table:
        raise _refuse(f"За столом места с 1 по {tournament.seats_per_table}")
    target = Seat(body.table, body.seat)
    if target in seating.values():
        raise _refuse(f"Стол {target.table}, место {target.seat} занято")
    _sit(registration, target)
    session.commit()
    return _state(session, tournament, now)
