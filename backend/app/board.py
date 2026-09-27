"""The hall board: a tournament as everyone in the club sees it on the TV, opened by the secret
link /board/<token> without login (ADR-0007). It shows no player names, only the blind clock and
how many players are left, so it is safe to leave on a public screen."""

import asyncio
from collections.abc import Callable
from datetime import datetime
from typing import NamedTuple, cast

import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app import realtime
from app.auth import Clock, Now
from app.db import SessionLocal
from app.game import clock_out, structure_of
from app.models import Club, Registration, Tournament
from app.schemas import BoardState, ClubOut, TournamentStatus

router = APIRouter(prefix="/api/board/{token}")


def average_stack(
    *,
    starting_stack: int,
    addon_stack: int | None,
    entries: int,
    addons: int,
    players_left: int,
) -> int | None:
    """Every entry (the first one and each re-entry) brings a starting stack and every add-on its
    chips; a knocked-out player's chips stay in play with the others."""
    if players_left == 0:
        return None
    chips = starting_stack * entries + (addon_stack or 0) * addons
    return round(chips / players_left)


def board_state(session: Session, tournament: Tournament, now: datetime) -> BoardState:
    seated = Registration.table_number.is_not(None)
    played = or_(seated, Registration.finish_order.is_not(None))
    players_left, players, reentries, addons = session.execute(
        select(
            func.count().filter(seated),
            func.count().filter(played),
            func.coalesce(func.sum(Registration.reentries), 0),
            func.coalesce(func.sum(Registration.addons), 0),
        ).where(Registration.tournament_id == tournament.id)
    ).one()
    club = session.get_one(Club, tournament.club_id)
    return BoardState(
        club=ClubOut.model_validate(club),
        name=tournament.name,
        starts_at=tournament.starts_at,
        status=cast(TournamentStatus, tournament.status),
        starting_stack=tournament.starting_stack,
        structure=structure_of(tournament),
        clock=clock_out(tournament, now),
        players_left=players_left,
        players=players,
        reentries=reentries,
        average_stack=average_stack(
            starting_stack=tournament.starting_stack,
            addon_stack=tournament.addon_stack,
            entries=players + reentries,
            addons=addons,
            players_left=players_left,
        ),
    )


def tournament_on_board(session: Session, token: str) -> Tournament | None:
    return session.scalar(select(Tournament).where(Tournament.board_token == token))


class _Found(NamedTuple):
    tournament_id: int
    board: BoardState


def _find_board(token: str, now: datetime) -> _Found | None:
    """The board with this secret code, read in a session of its own: a board stays connected
    for hours, and a session held that long would keep a connection from the pool."""
    with SessionLocal() as session:
        tournament = tournament_on_board(session, token)
        if tournament is None:
            return None
        return _Found(tournament.id, board_state(session, tournament, now))


@router.get("")
def get_board(token: str, now: Now) -> BoardState:
    found = _find_board(token, now)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Табло не найдено")
    return found.board


async def _send_on_change(
    websocket: WebSocket, token: str, changed: asyncio.Event, clock: Callable[[], datetime]
) -> None:
    while True:
        await changed.wait()
        changed.clear()
        found = await run_in_threadpool(_find_board, token, clock())
        assert found is not None, "tournaments are never deleted"
        try:
            await websocket.send_text(found.board.model_dump_json())
        except (WebSocketDisconnect, OSError):
            return  # The board has gone; _until_disconnected hears of it.


async def _until_disconnected(websocket: WebSocket) -> None:
    # The board sends nothing; anything it does send is ignored.
    while (await websocket.receive())["type"] != "websocket.disconnect":
        pass


@router.websocket("/ws")
async def board_updates(websocket: WebSocket, token: str, clock: Clock) -> None:
    """The board as it is on connecting, then again after every change of the tournament.
    A board that lost its connection connects again and so gets the board as it is now."""
    await websocket.accept()
    found = await run_in_threadpool(_find_board, token, clock())
    if found is None:
        # Closed only once accepted: a browser sees a refused connection as a network failure
        # and could not tell a wrong link from a lost connection.
        await websocket.close(code=4404, reason="Табло не найдено")
        return
    # Watching starts before the first board is read, so no change can slip in between.
    with realtime.watching(found.tournament_id) as changed:
        changed.set()
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(_send_on_change, websocket, token, changed, clock)
            await _until_disconnected(websocket)
            tasks.cancel_scope.cancel()
