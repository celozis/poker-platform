"""The action log: who did what at the club, when and to which player, so that a disputed moment
of a tournament can be put together again. See docs/adr/ADR-0014-action-log.md. The admin reads
a tournament's log in app/tournament_log.py.

Every action writes its own entry with `record`, in the transaction that makes the change, so
an action is logged if and only if it is done. Entries are only ever added: there is no way to
change or delete one."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.models import ActionLogEntry, Admin, Club, Tournament, Transaction
from app.schemas import LoggedAction
from app.transactions import PAID_BY, roubles


def record(
    session: Session,
    done_to: Tournament | Club,
    admin: Admin | None,
    action: LoggedAction,
    now: datetime,
    *,
    player_id: int | None = None,
    details: str = "",
) -> None:
    """Logs the action done to the tournament, or to the club itself (its team, its settings):
    by the admin, or by the player themselves (None). Called before the action's commit."""
    if isinstance(done_to, Tournament):
        club_id, tournament_id = done_to.club_id, done_to.id
    else:
        club_id, tournament_id = done_to.id, None
    session.add(
        ActionLogEntry(
            club_id=club_id,
            tournament_id=tournament_id,
            admin_id=None if admin is None else admin.id,
            player_id=player_id,
            action=action,
            details=details,
            created_at=now,
        )
    )


def paid(transaction: Transaction | None) -> str:
    """The details of an action the player paid for: "2 000 ₽ наличными"; nothing when free."""
    if transaction is None:
        return ""
    return f"{roubles(transaction.amount)} {PAID_BY[transaction.payment_method]}"


def given_back(amount: int) -> str:
    """The details of an action that gave the player's money back, if any."""
    return f"Возвращено {roubles(amount)}" if amount else ""
