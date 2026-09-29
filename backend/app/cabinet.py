"""The player's web cabinet: a player logs in by phone and a one-time code, as an admin does
(app/auth.py), and sees their own profile, rating, tournaments and their clubs' schedules.

Which player is shown comes from the session alone: no address takes a player's id, so there is
no way to ask for someone else's data. The cabinet's session opens nothing of the admin panel's,
and an admin's session nothing of the cabinet's."""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.auth import (
    SESSION_TTL,
    CodeRequest,
    CodeVerification,
    DbSession,
    Now,
    hash_secret,
    new_session_token,
    normalize_phone,
    send_login_code,
    take_login_code,
)
from app.models import (
    Club,
    ClubPlayer,
    Player,
    PlayerSession,
    Registration,
    TelegramUser,
    Tournament,
)
from app.rating import club_standings
from app.schemas import (
    CabinetClub,
    CabinetPlayer,
    CabinetRating,
    ClubOut,
    PlayerCabinet,
    SeasonOut,
    TournamentPlayed,
    ScheduledTournament,
)
from app.schedule import club_schedule
from app.seasons import Season, season_at

router = APIRouter(prefix="/api/cabinet")

SESSION_COOKIE = "player_session"
# Only the cabinet's own addresses get the cookie. Shared by set_cookie and delete_cookie: a cookie
# is only deleted if these match.
SESSION_COOKIE_SCOPE: dict[str, Any] = {
    "path": "/api/cabinet",
    "httponly": True,
    "samesite": "strict",
}
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


@router.post("/request-code", status_code=status.HTTP_204_NO_CONTENT)
def request_code(body: CodeRequest, session: DbSession, now: Now) -> None:
    phone = normalize_phone(body.phone)
    if phone is None or session.scalar(select(Player.id).where(Player.phone == phone)) is None:
        # Unknown numbers get the same answer, so the endpoint does not reveal who plays.
        return
    send_login_code(session, "cabinet", phone, now)


@router.post("/verify-code", status_code=status.HTTP_204_NO_CONTENT)
def verify_code(body: CodeVerification, response: Response, session: DbSession, now: Now) -> None:
    phone = normalize_phone(body.phone)
    player = session.scalar(select(Player).where(Player.phone == phone)) if phone else None
    if player is None or not take_login_code(session, "cabinet", player.phone, body.code, now):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный или просроченный код")
    token, token_hash = new_session_token()
    session.add(
        PlayerSession(token_hash=token_hash, player_id=player.id, expires_at=now + SESSION_TTL)
    )
    session.commit()
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), **SESSION_COOKIE_SCOPE
    )


def current_player(session: DbSession, now: Now, token: SessionToken = None) -> Player:
    stored = session.get(PlayerSession, hash_secret(token)) if token else None
    if stored is None or stored.expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход")
    return stored.player


CurrentPlayer = Annotated[Player, Depends(current_player)]


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, session: DbSession, token: SessionToken = None) -> None:
    if token:
        session.execute(delete(PlayerSession).where(PlayerSession.token_hash == hash_secret(token)))
        session.commit()
    response.delete_cookie(SESSION_COOKIE, **SESSION_COOKIE_SCOPE)


def _own_rating(session: Session, club: Club, player: Player, season: Season) -> CabinetRating | None:
    """The player's position and points in the club's rating of the season, as the club's admins
    see it; none of the other players' rows."""
    standings = club_standings(session, club.id, season.starts_at, season.ends_at)
    own = next((row for row in standings if row.player.id == player.id), None)
    if own is None:
        return None
    return CabinetRating(position=own.position, points=own.points, tournaments=own.tournaments)


def _schedule(
    session: Session, club: Club, player: Player, now: datetime
) -> list[ScheduledTournament]:
    tournaments = club_schedule(session, club.id, now)
    registered = set(
        session.scalars(
            select(Registration.tournament_id).where(
                Registration.player_id == player.id,
                Registration.tournament_id.in_([t.id for t in tournaments]),
            )
        )
    )
    return [
        ScheduledTournament(
            name=t.name,
            starts_at=t.starts_at,
            buy_in=t.buy_in,
            going_on=t.is_live,
            registered=t.id in registered,
        )
        for t in tournaments
    ]


def _history(session: Session, player: Player) -> list[TournamentPlayed]:
    """The finished tournaments the player has a result in, in any club, the latest first."""
    field = (
        select(Registration.tournament_id, func.count().label("players"))
        .where(Registration.place.is_not(None))
        .group_by(Registration.tournament_id)
        .subquery()
    )
    rows = session.execute(
        select(Registration, Tournament, Club.name, field.c.players)
        .join(Tournament, Tournament.id == Registration.tournament_id)
        .join(Club, Club.id == Tournament.club_id)
        .join(field, field.c.tournament_id == Tournament.id)
        .where(
            Registration.player_id == player.id,
            Tournament.status == "finished",
            Registration.place.is_not(None),
        )
        .order_by(Tournament.starts_at.desc(), Tournament.id.desc())
    ).all()
    return [
        TournamentPlayed(
            starts_at=tournament.starts_at,
            tournament=tournament.name,
            club=club_name,
            place=registration.place,
            players=players,
            points=registration.points,
            reentries=registration.reentries,
            addons=registration.addons,
        )
        for registration, tournament, club_name, players in rows
    ]


@router.get("")
def cabinet(player: CurrentPlayer, session: DbSession, now: Now) -> PlayerCabinet:
    season = season_at(now)
    clubs = session.scalars(
        select(Club)
        .join(ClubPlayer, ClubPlayer.club_id == Club.id)
        .where(ClubPlayer.player_id == player.id)
        .order_by(ClubPlayer.added_at, Club.id)
    )
    telegram = select(TelegramUser.telegram_id).where(TelegramUser.player_id == player.id)
    return PlayerCabinet(
        player=CabinetPlayer(
            name=player.name,
            phone=player.phone,
            telegram_linked=session.scalar(telegram) is not None,
        ),
        season=SeasonOut.model_validate(season),
        history=_history(session, player),
        clubs=[
            CabinetClub(
                club=ClubOut.model_validate(club),
                rating=_own_rating(session, club, player, season),
                schedule=_schedule(session, club, player, now),
            )
            for club in clubs
        ],
    )
