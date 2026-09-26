"""The club's players. A player belongs to the whole league, and each club keeps its own list of
the players who have been to it (ClubPlayer). An admin only ever sees their club's list (ADR-0003)."""

import re

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.dialects.postgresql import insert

from app.auth import DbSession, Now, normalize_phone
from app.clubs import AdminClub
from app.models import ClubPlayer, Player
from app.schemas import AddPlayerOutcome, PlayerAdded, PlayerIn, PlayerOut

router = APIRouter(prefix="/api/clubs/{club_id}/players")

MAX_NAME_LENGTH = 200  # models.Player.name
# "8 913" is enough to read a leading 8 as the start of a +7 number.
MIN_DIGITS_FOR_PREFIX = 4


def _player_errors(player: PlayerIn, phone: str | None) -> list[str]:
    errors: list[str] = []
    if not player.name:
        errors.append("Укажите имя игрока")
    if len(player.name) > MAX_NAME_LENGTH:
        errors.append(f"Имя длиннее {MAX_NAME_LENGTH} символов")
    if phone is None:
        errors.append("Телефон: нужен российский номер из 11 цифр, например +7 913 555-12-34")
    if not player.consent:
        errors.append("Без согласия на обработку персональных данных игрока завести нельзя")
    return errors


def _matching(query: str) -> ColumnElement[bool]:
    """Players whose name contains the query, or whose phone contains the digits typed."""
    escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    conditions: list[ColumnElement[bool]] = [Player.name.ilike(f"%{escaped}%", escape="\\")]
    digits = re.sub(r"\D", "", query)
    if digits:
        conditions.append(Player.phone.contains(digits))
        if digits.startswith("8") and len(digits) >= MIN_DIGITS_FOR_PREFIX:
            # "8 913 ..." is how a number starting with +7 is often typed. A short "8" alone
            # would otherwise match every number.
            conditions.append(Player.phone.startswith("+7" + digits[1:]))
    return or_(*conditions)


@router.get("")
def list_players(club: AdminClub, session: DbSession, q: str = "") -> list[PlayerOut]:
    """The club's players in name order; `q` narrows them down by name or phone."""
    statement = (
        select(Player)
        .join(ClubPlayer, ClubPlayer.player_id == Player.id)
        .where(ClubPlayer.club_id == club.id)
        .order_by(Player.name, Player.id)
    )
    if q.strip():
        statement = statement.where(_matching(q.strip()))
    return [PlayerOut.model_validate(player) for player in session.scalars(statement)]


@router.post("", status_code=status.HTTP_201_CREATED)
def add_player(
    body: PlayerIn, club: AdminClub, session: DbSession, now: Now, response: Response
) -> PlayerAdded:
    phone = normalize_phone(body.phone)
    errors = _player_errors(body, phone)
    if errors or phone is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, errors)
    # One player per phone across the league: a known phone brings the existing player into
    # the club, keeping their name. ON CONFLICT also covers two admins adding the same phone at once.
    created = session.scalar(
        insert(Player)
        .values(name=body.name, phone=phone, consent_given_at=now)
        .on_conflict_do_nothing(index_elements=[Player.phone])
        .returning(Player.id)
    )
    player = session.scalars(select(Player).where(Player.phone == phone)).one()
    joined = session.scalar(
        insert(ClubPlayer)
        .values(club_id=club.id, player_id=player.id, added_at=now)
        .on_conflict_do_nothing()
        .returning(ClubPlayer.player_id)
    )
    session.commit()
    if created is None:
        response.status_code = status.HTTP_200_OK
    outcome: AddPlayerOutcome = (
        "created" if created is not None else "added_to_club" if joined is not None else "already_in_club"
    )
    return PlayerAdded(player=PlayerOut.model_validate(player), outcome=outcome)
