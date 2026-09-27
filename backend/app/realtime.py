"""Tells whoever watches a tournament live (the hall board) that it has changed.

A change only says "tournament N has changed": each watcher then reads the tournament afresh.
So a watcher always ends on the latest committed state, however the notices of two quick
changes overtake each other, and several changes in a row are sent as one (ADR-0007).

The watchers live in this process's memory, so this works while the backend runs as one
process; more processes would need PostgreSQL LISTEN/NOTIFY or a message broker instead."""

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


@dataclass(eq=False)
class _Watcher:
    loop: asyncio.AbstractEventLoop
    changed: asyncio.Event = field(default_factory=asyncio.Event)


# Watchers are added in the event loop and told of changes from the request threads.
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


def tournament_changed(tournament_id: int) -> None:
    """Tells the tournament's watchers it has changed. Called after the change is committed,
    from any thread."""
    with _lock:
        watchers = list(_watchers.get(tournament_id, ()))
    for watcher in watchers:
        try:
            watcher.loop.call_soon_threadsafe(watcher.changed.set)
        except RuntimeError:
            pass  # The watcher's loop has closed; it is leaving anyway.
