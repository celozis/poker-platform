"""The league command: what is the league's to decide — which clubs there are, their names and
who owns each — done by the developer at the league's request, inside the backend's container:

    python -m app.league clubs
    python -m app.league create-club "Покер-клуб «Томь»" --primary "#1F5C4A" --accent "#D9B44A"
    python -m app.league rename-club 3 "Покер-клуб «Томь-Арена»"
    python -m app.league appoint-owner 3 "Наталья Широкова" "+7 999 000-00-13"
    python -m app.league dismiss-owner "+7 999 000-00-13"

The functions below are what the network owner's screen will call later; the owners are taken on
and let go by the same functions as the club's team (app/team.py)."""

import argparse
import re
import sys
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import action_log
from app.action_log import member_details
from app.auth import normalize_phone
from app.db import SessionLocal
from app.models import Admin, Club
from app.team import TeamInvalid, TeamRefusal, let_go, take_on

# A new club's look until its owner sets its own: the league's mark and colours.
DEFAULT_LOGO = "/logos/league.svg"
DEFAULT_PRIMARY = "#0F172A"
DEFAULT_ACCENT = "#F59E0B"
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")
MAX_NAME_LENGTH = 200  # models.Club.name


class LeagueRefusal(Exception):
    """Why the league's change cannot be made, in words for the developer."""


def clubs_and_owners(session: Session) -> list[tuple[Club, list[Admin]]]:
    """Every club of the league in the order they were created, with its owners (not those
    dismissed) in name order."""
    owners = session.scalars(
        select(Admin)
        .where(Admin.role == "owner", Admin.removed_at.is_(None))
        .order_by(Admin.name, Admin.id)
    ).all()
    return [
        (club, [owner for owner in owners if owner.club_id == club.id])
        for club in session.scalars(select(Club).order_by(Club.id))
    ]


def _club_name(session: Session, name: str) -> str:
    """The name, if it can be a club's: given, and no other club's already."""
    name = name.strip()
    if not name:
        raise LeagueRefusal("Укажите название клуба")
    if len(name) > MAX_NAME_LENGTH:
        raise LeagueRefusal(f"Название длиннее {MAX_NAME_LENGTH} символов")
    taken = session.scalar(select(Club).where(Club.name == name))
    if taken is not None:
        raise LeagueRefusal(f"Клуб «{name}» уже есть (№ {taken.id})")
    return name


def found_club(session: Session, name: str, primary_color: str, accent_color: str) -> Club:
    """A new club of the league, with the league's logo until its owner sets one. Called before
    the caller's commit."""
    for color in (primary_color, accent_color):
        if not HEX_COLOR.match(color):
            raise LeagueRefusal(f"Цвет {color}: нужен вид #RRGGBB, например #0B3D91")
    club = Club(
        name=_club_name(session, name),
        logo_url=DEFAULT_LOGO,
        primary_color=primary_color,
        accent_color=accent_color,
    )
    session.add(club)
    session.flush()
    return club


def rename_club(session: Session, club: Club, name: str, now: datetime) -> None:
    """Gives the club a new name, logged in its log. Called before the caller's commit."""
    was, club.name = club.name, _club_name(session, name)
    action_log.record(
        session, club, None, "club_renamed", now, details=f"{was} → {club.name}", by_league=True
    )


def appoint_owner(session: Session, club: Club, name: str, phone: str, now: datetime) -> Admin:
    """Makes the person an owner of the club. Called before the caller's commit."""
    owner, _ = take_on(session, club, name, phone, "owner", None, now)
    return owner


def dismiss_owner(session: Session, phone: str, now: datetime) -> Admin:
    """Takes the owner with this phone out of their club's team: they no longer log in. Called
    before the caller's commit."""
    normalized = normalize_phone(phone)
    owner = session.scalar(
        select(Admin).where(
            Admin.phone == normalized, Admin.role == "owner", Admin.removed_at.is_(None)
        )
    )
    if owner is None:
        raise LeagueRefusal(f"Владельца с телефоном {phone} нет ни в одном клубе")
    let_go(session, owner, None, now)
    return owner


def _club(session: Session, number: int) -> Club:
    club = session.get(Club, number)
    if club is None:
        raise LeagueRefusal(f"Клуба № {number} нет. Список клубов: python -m app.league clubs")
    return club


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.league", description="Клубы лиги и их владельцы."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("clubs", help="список клубов с владельцами")
    create = commands.add_parser("create-club", help="завести клуб")
    create.add_argument("name", help="название клуба")
    create.add_argument("--primary", default=DEFAULT_PRIMARY, help="основной цвет, #RRGGBB")
    create.add_argument("--accent", default=DEFAULT_ACCENT, help="акцентный цвет, #RRGGBB")
    rename = commands.add_parser("rename-club", help="переименовать клуб")
    rename.add_argument("club", type=int, help="номер клуба из списка clubs")
    rename.add_argument("name", help="новое название")
    appoint = commands.add_parser("appoint-owner", help="назначить владельца клуба")
    appoint.add_argument("club", type=int, help="номер клуба из списка clubs")
    appoint.add_argument("name", help="имя и фамилия")
    appoint.add_argument("phone", help="телефон, по которому он входит в админ-панель")
    dismiss = commands.add_parser("dismiss-owner", help="снять владельца: он больше не входит")
    dismiss.add_argument("phone", help="телефон владельца")
    return parser


def _run(session: Session, arguments: argparse.Namespace, now: datetime) -> str:
    """Does what the command says and tells what was done."""
    match arguments.command:
        case "clubs":
            lines = []
            for club, owners in clubs_and_owners(session):
                lines.append(
                    f"№ {club.id} {club.name}, цвета {club.primary_color} и {club.accent_color}"
                )
                lines += [f"    владелец: {member_details(owner)}" for owner in owners]
                if not owners:
                    lines.append("    владельца нет")
            return "\n".join(lines)
        case "create-club":
            club = found_club(session, arguments.name, arguments.primary, arguments.accent)
            session.commit()
            return f"Клуб заведён: {club.name} (№ {club.id})"
        case "rename-club":
            club = _club(session, arguments.club)
            rename_club(session, club, arguments.name, now)
            session.commit()
            return f"Клуб № {club.id} теперь называется {club.name}"
        case "appoint-owner":
            club = _club(session, arguments.club)
            owner = appoint_owner(session, club, arguments.name, arguments.phone, now)
            session.commit()
            return f"Владелец клуба {club.name} (№ {club.id}): {member_details(owner)}"
        case "dismiss-owner":
            owner = dismiss_owner(session, arguments.phone, now)
            session.commit()
            return f"Владелец клуба {owner.club.name} снят: {member_details(owner)}"
    raise AssertionError(arguments.command)


def main(argv: list[str] | None = None) -> int:
    """Runs the command; 0 when it was done, 1 when it was refused (the reason is printed)."""
    arguments = _parser().parse_args(argv)
    with SessionLocal() as session:
        try:
            print(_run(session, arguments, datetime.now(UTC)))
        except (LeagueRefusal, TeamRefusal, TeamInvalid) as refusal:
            print(f"Не сделано: {refusal}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
