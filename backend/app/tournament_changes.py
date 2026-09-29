"""The admin panel's live signal "the tournament has changed", over a WebSocket: after every
change, the admin panel's own or a player's in the Telegram bot, the server sends `changed`, and
the panel reads what it shows afresh (ADR-0011).

Only the club's own admin may watch (ADR-0003). A WebSocket has no dependencies that hold a
database session: one held for the hours the page stays open would keep a connection from the
pool, so the admin and the tournament are checked in a session of their own."""

from datetime import datetime

import anyio
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select

from app import realtime
from app.auth import SESSION_COOKIE, Clock, current_admin
from app.db import SessionLocal
from app.models import Tournament

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments/{tournament_id}")

CHANGED = "changed"


def _may_watch(token: str | None, club_id: int, tournament_id: int, now: datetime) -> bool:
    """Whether the logged-in admin is the club's and the tournament is the club's."""
    with SessionLocal() as session:
        try:
            admin = current_admin(session, now, token)
        except HTTPException:
            return False
        return admin.club_id == club_id and session.scalar(
            select(Tournament.id).where(
                Tournament.id == tournament_id, Tournament.club_id == club_id
            )
        ) is not None


@router.websocket("/ws")
async def tournament_changes(
    websocket: WebSocket, club_id: int, tournament_id: int, clock: Clock
) -> None:
    token = websocket.cookies.get(SESSION_COOKIE)
    if not await run_in_threadpool(_may_watch, token, club_id, tournament_id, clock()):
        # Accepted and then closed, so that the browser sees why, as the hall board does.
        await websocket.accept()
        await websocket.close(code=4403, reason="Нет доступа к турниру")
        return
    # Watching starts before the connection is accepted, so no change after it can slip by.
    with realtime.watching(tournament_id) as changed:
        await websocket.accept()
        async with anyio.create_task_group() as tasks:

            async def send_on_change() -> None:
                while True:
                    await changed.wait()
                    changed.clear()
                    try:
                        await websocket.send_text(CHANGED)
                    except (WebSocketDisconnect, OSError):
                        return  # The page has gone; the receiving side hears of it.

            tasks.start_soon(send_on_change)
            # The page sends nothing; anything it does send is ignored.
            while (await websocket.receive())["type"] != "websocket.disconnect":
                pass
            tasks.cancel_scope.cancel()
