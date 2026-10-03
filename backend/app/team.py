"""The club's team: its owners and admins as the owner sees them. The owner adds an admin and
removes one; owners are the league's to change (app/league.py, which takes people on and lets
them go with the same functions).

Club-scoped like everything under /api/clubs/{club_id} (ADR-0003), and the owner's alone
(OwnerClub)."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import action_log
from app.action_log import member_details
from app.auth import PHONE_FORMAT, CurrentAdmin, DbSession, Now, normalize_phone
from app.clubs import OwnerClub
from app.models import Admin, AdminSession, Club
from app.schemas import (
    AdminOut,
    AdminRole,
    LoggedAction,
    TeamMemberAdded,
    TeamMemberIn,
)

router = APIRouter(prefix="/api/clubs/{club_id}/team")

# added: new to the league; returned: removed from this club's team before, now back; promoted:
# an admin of the club made its owner, which only the league does (app/league.py).
TakeOnOutcome = Literal["added", "returned", "promoted"]

OTHER_CLUBS_STAFF = (
    "Этот телефон уже у сотрудника другого клуба лиги. Один человек может быть в команде только "
    "одного клуба"
)
MAX_NAME_LENGTH = 200  # models.Admin.name


class TeamInvalid(Exception):
    """What is wrong with the name or the phone typed, one message each."""

    def __init__(self, errors: list[str]) -> None:
        super().__init__("; ".join(errors))
        self.errors = errors


class TeamRefusal(Exception):
    """Why the team cannot be changed so, in words for the owner (or the developer at the
    league's request)."""


def take_on(
    session: Session,
    club: Club,
    name: str,
    raw_phone: str,
    role: AdminRole,
    by: Admin | None,
    now: datetime,
) -> tuple[Admin, TakeOnOutcome]:
    """Takes the person on in the club's team in the role: someone new, or someone removed from
    this club's team before, who comes back under the name the club knew them by. Logged in the
    club's log as done by `by`, the owner, or the league (None). Called before the caller's
    commit."""
    name = name.strip()
    phone = normalize_phone(raw_phone)
    errors = []
    if not name:
        errors.append("Укажите имя сотрудника")
    if len(name) > MAX_NAME_LENGTH:
        errors.append(f"Имя длиннее {MAX_NAME_LENGTH} символов")
    if phone is None:
        errors.append(PHONE_FORMAT)
    if errors:
        raise TeamInvalid(errors)
    member = session.scalar(select(Admin).where(Admin.phone == phone).with_for_update())
    if member is not None and member.club_id != club.id:
        # A phone is one staff member's across the league, removed ones too: their row stays.
        raise TeamRefusal(OTHER_CLUBS_STAFF)
    outcome: TakeOnOutcome
    if member is not None and member.removed_at is None:
        if member.role != "admin" or role != "owner":
            raise TeamRefusal(f"{member.name} уже в команде клуба")
        # The league makes one of the club's admins its owner.
        member.role = role
        outcome = "promoted"
    elif member is not None:
        member.removed_at = None
        member.role = role
        outcome = "returned"
    else:
        member = Admin(club_id=club.id, phone=phone, name=name, role=role)
        session.add(member)
        session.flush()
        outcome = "added"
    action: LoggedAction = (
        "owner_appointed"
        if role == "owner"
        else "admin_added" if outcome == "added" else "admin_returned"
    )
    action_log.record(
        session, club, by, action, now, details=member_details(member), by_league=by is None
    )
    return member, outcome


def let_go(session: Session, member: Admin, by: Admin | None, now: datetime) -> None:
    """Removes the member from the club's team: they no longer log in, and every session of
    theirs ends at once. The row stays, so the cashier and the log keep their name. Logged in the
    club's log as done by `by`, the owner, or the league (None). Called before the caller's
    commit."""
    member.removed_at = now
    session.execute(delete(AdminSession).where(AdminSession.admin_id == member.id))
    action: LoggedAction = "owner_dismissed" if member.role == "owner" else "admin_removed"
    action_log.record(
        session, member.club, by, action, now, details=member_details(member), by_league=by is None
    )


@router.get("")
def get_team(club: OwnerClub, session: DbSession) -> list[AdminOut]:
    """The club's owners, then its admins, each in name order."""
    members = session.scalars(
        select(Admin)
        .where(Admin.club_id == club.id, Admin.removed_at.is_(None))
        # "owner" sorts after "admin".
        .order_by(Admin.role.desc(), Admin.name, Admin.id)
    )
    return [AdminOut.model_validate(member) for member in members]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_admin(
    body: TeamMemberIn,
    club: OwnerClub,
    owner: CurrentAdmin,
    session: DbSession,
    now: Now,
    response: Response,
) -> TeamMemberAdded:
    try:
        member, outcome = take_on(session, club, body.name, body.phone, "admin", owner, now)
    except TeamInvalid as invalid:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, invalid.errors) from invalid
    except TeamRefusal as refusal:
        raise HTTPException(status.HTTP_409_CONFLICT, str(refusal)) from refusal
    session.commit()
    # Taken on as an admin, nobody is promoted.
    assert outcome != "promoted"
    if outcome == "returned":
        response.status_code = status.HTTP_200_OK
    return TeamMemberAdded(admin=AdminOut.model_validate(member), outcome=outcome)


@router.delete("/{admin_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_admin(
    admin_id: int, club: OwnerClub, owner: CurrentAdmin, session: DbSession, now: Now
) -> None:
    member = session.get(Admin, admin_id)
    if member is None or member.club_id != club.id or member.removed_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Такого сотрудника в команде клуба нет")
    if member.role == "owner":
        # The owner sees the club's money: who owns the club is the league's to say.
        raise HTTPException(status.HTTP_409_CONFLICT, "Владельцев клуба меняет лига")
    let_go(session, member, owner, now)
    session.commit()
