"""The club's own log as its owner reads it: what was done to the club rather than to one of its
tournaments, such as changes of its team (app/action_log.py records it). Club-scoped like
everything under /api/clubs/{club_id} (ADR-0003), and the owner's alone, as the team is. There is
only reading: an entry can be neither changed nor deleted (ADR-0014)."""

from fastapi import APIRouter
from sqlalchemy import select

from app.auth import DbSession
from app.clubs import OwnerClub
from app.models import ActionLogEntry
from app.schemas import ActionLogEntryOut

router = APIRouter(prefix="/api/clubs/{club_id}/log")


@router.get("")
def get_club_log(club: OwnerClub, session: DbSession) -> list[ActionLogEntryOut]:
    """The club's log, the latest first."""
    log = session.scalars(
        select(ActionLogEntry)
        .where(ActionLogEntry.club_id == club.id, ActionLogEntry.tournament_id.is_(None))
        .order_by(ActionLogEntry.id.desc())
    )
    return [ActionLogEntryOut.model_validate(entry) for entry in log]
