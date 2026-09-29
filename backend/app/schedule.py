"""A club's schedule: the tournaments a player can still sign up for, the soonest first. The
Telegram bot shows it (app/bot/conversation.py), and so does the player's web cabinet
(app/cabinet.py)."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.game import late_registration_closed_because
from app.models import Tournament
from app.registrations import CHECK_IN_WINDOW

# The soonest tournaments a schedule shows: enough for a couple of weeks, and one bot message
# stays well within Telegram's 4096 characters.
SCHEDULE_LENGTH = 10


def club_schedule(session: Session, club_id: int, now: datetime) -> list[Tournament]:
    """Those that have not started yet, and those going on while their late registration is open.
    One the admin has neither started nor cancelled goes once the player can no longer come to
    it: its check-in closes CHECK_IN_WINDOW after its start."""
    coming = session.scalars(
        select(Tournament)
        .where(
            Tournament.club_id == club_id,
            Tournament.status == "scheduled",
            Tournament.starts_at >= now - CHECK_IN_WINDOW,
        )
        .order_by(Tournament.starts_at, Tournament.id)
        .limit(SCHEDULE_LENGTH)
    ).all()
    live = [
        t
        for t in session.scalars(
            select(Tournament).where(
                Tournament.club_id == club_id,
                Tournament.status.in_(["running", "paused"]),
                Tournament.late_registration_until_level.is_not(None),
            )
        )
        if late_registration_closed_because(t, now) is None
    ]
    return sorted([*live, *coming], key=lambda t: (t.starts_at, t.id))[:SCHEDULE_LENGTH]
