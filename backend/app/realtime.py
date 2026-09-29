"""Tells whoever watches a tournament live (the hall board, the admin panel) that it has changed,
whichever process changed it: a backend process or the Telegram bot (ADR-0011).

A change only says "tournament N has changed": each watcher then reads the tournament afresh.
So a watcher always ends on the latest committed state, however the notices of two quick
changes overtake each other, and several changes in a row are sent as one (ADR-0007).

The notice goes through PostgreSQL: the change sends NOTIFY in its own transaction, which
PostgreSQL delivers once that commits, and drops if it rolls back. Every backend process LISTENs
on one connection of its own while it runs (`listening`) and wakes its watchers, which live in
its memory."""

import asyncio
import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg
from sqlalchemy import func, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.config import database_url

logger = logging.getLogger("app.realtime")

CHANNEL = "tournament_changed"
# How long the listener waits for a notice before it looks whether it is to stop.
_POLL_SECONDS = 0.2
# How long a lost connection is left before connecting again.
_RECONNECT_SECONDS = 1.0


@dataclass(eq=False)
class _Watcher:
    loop: asyncio.AbstractEventLoop
    changed: asyncio.Event = field(default_factory=asyncio.Event)


# Watchers are added in the event loop and woken from the listener's thread.
_lock = threading.Lock()
_watchers: dict[int, set[_Watcher]] = {}


@contextmanager
def watching(tournament_id: int) -> Iterator[asyncio.Event]:
    """An event that is set whenever the tournament changes, until the block is left. Called in
    the event loop that waits for it."""
    watcher = _Watcher(asyncio.get_running_loop())
    with _lock:
        _watchers.setdefault(tournament_id, set()).add(watcher)
    try:
        yield watcher.changed
    finally:
        with _lock:
            _watchers[tournament_id].discard(watcher)
            if not _watchers[tournament_id]:
                del _watchers[tournament_id]


def tournament_changed(session: Session, tournament_id: int) -> None:
    """Tells the tournament's watchers in every process that it has changed, once the session
    commits. Called before the commit, in the transaction that makes the change."""
    session.execute(select(func.pg_notify(CHANNEL, str(tournament_id))))


def _wake(tournament_ids: list[int] | None) -> None:
    """Wakes the watchers of these tournaments, or of all of them."""
    with _lock:
        watchers = [
            watcher
            for tournament_id, of_tournament in _watchers.items()
            if tournament_ids is None or tournament_id in tournament_ids
            for watcher in of_tournament
        ]
    for watcher in watchers:
        try:
            watcher.loop.call_soon_threadsafe(watcher.changed.set)
        except RuntimeError:
            pass  # The watcher's loop has closed; it is leaving anyway.


def _listen(stop: threading.Event, ready: threading.Event) -> None:
    conninfo = make_url(database_url()).set(drivername="postgresql")
    while not stop.is_set():
        try:
            with psycopg.connect(
                conninfo.render_as_string(hide_password=False), autocommit=True
            ) as connection:
                connection.execute(f"LISTEN {CHANNEL}")
                ready.set()
                # Changes made while not listening were not heard: everyone reads afresh.
                _wake(None)
                while not stop.is_set():
                    for notice in connection.notifies(timeout=_POLL_SECONDS):
                        _wake([int(notice.payload)])
        except Exception:
            # Whatever went wrong, the listener must go on: without it no screen hears a change.
            logger.warning("Нет связи с базой для уведомлений о турнирах, повторим", exc_info=True)
            stop.wait(_RECONNECT_SECONDS)


_listener_lock = threading.Lock()
_listener_users = 0
_listener_stop = threading.Event()
_listener: threading.Thread | None = None


@contextmanager
def listening() -> Iterator[None]:
    """Hears the notices of every process while the block runs, as the backend does while it
    serves. One listener per process, however many blocks run at once (tests run several apps)."""
    global _listener, _listener_users, _listener_stop
    with _listener_lock:
        _listener_users += 1
        if _listener is None:
            _listener_stop = threading.Event()
            ready = threading.Event()
            _listener = threading.Thread(
                target=_listen, args=(_listener_stop, ready), name="realtime", daemon=True
            )
            _listener.start()
            # Changes made from now on are heard; a database still starting is waited for no
            # longer than this, and the listener goes on trying.
            ready.wait(timeout=5)
    try:
        yield
    finally:
        with _listener_lock:
            _listener_users -= 1
            if _listener_users == 0 and _listener is not None:
                _listener_stop.set()
                _listener.join()
                _listener = None
