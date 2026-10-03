"""A tournament's action log as the admin reads it: who did what, when and to which player
(app/action_log.py records it). Club-scoped like everything under /api/clubs/{club_id}
(ADR-0003). There is only reading: an entry can be neither changed nor deleted."""

from fastapi import APIRouter
from sqlalchemy import select

from app.auth import DbSession
from app.clubs import AdminClub
from app.models import ActionLogEntry
from app.schemas import ActionLogEntryOut
from app.tournaments import club_tournament

router = APIRouter(prefix="/api/clubs/{club_id}/tournaments/{tournament_id}/log")


@router.get("")
def get_log(
    tournament_id: int, club: AdminClub, session: DbSession, player_id: int | None = None
) -> list[ActionLogEntryOut]:
    """The tournament's log, the latest first; only what was done to the player, if one is given."""
    tournament = club_tournament(session, club, tournament_id)
    statement = select(ActionLogEntry).where(ActionLogEntry.tournament_id == tournament.id)
    if player_id is not None:
        statement = statement.where(ActionLogEntry.player_id == player_id)
    log = session.scalars(statement.order_by(ActionLogEntry.id.desc())).all()
    return [ActionLogEntryOut.model_validate(entry) for entry in log]
