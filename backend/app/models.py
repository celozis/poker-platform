from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Interval, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    logo_url: Mapped[str] = mapped_column(String(500))
    primary_color: Mapped[str] = mapped_column(String(7))
    accent_color: Mapped[str] = mapped_column(String(7))


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Every club-owned row carries club_id, see docs/adr/ADR-0003-multi-tenancy.md.
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    phone: Mapped[str] = mapped_column(String(16), unique=True)
    name: Mapped[str] = mapped_column(String(200))

    club: Mapped[Club] = relationship()


class LoginCode(Base):
    """The one pending login code for a phone number; requesting a new code replaces it."""

    __tablename__ = "login_codes"

    phone: Mapped[str] = mapped_column(String(16), primary_key=True)
    code_hash: Mapped[str] = mapped_column(String(64))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    failed_attempts: Mapped[int] = mapped_column(default=0)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admins.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    admin: Mapped[Admin] = relationship()


class Tournament(Base):
    __tablename__ = "tournaments"

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    buy_in: Mapped[int]
    starting_stack: Mapped[int]
    # Levels and breaks in play order (schemas.StructureItem), read and saved as a whole;
    # see docs/adr/ADR-0004-blind-structure-storage.md.
    structure: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    reentry_until_level: Mapped[int | None]
    addon_at_level: Mapped[int | None]
    late_registration_until_level: Mapped[int | None]
    seats_per_table: Mapped[int] = mapped_column(default=9)
    # scheduled → running ⇄ paused → finished; or scheduled → cancelled.
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # The blind clock (app/blind_clock.py) once the tournament has started: the structure item
    # being played and when it ends (running) or how much of it is left (paused).
    clock_item: Mapped[int | None]
    clock_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    clock_remaining: Mapped[timedelta | None] = mapped_column(Interval)

    @property
    def has_started(self) -> bool:
        return self.status in ("running", "paused", "finished")

    @property
    def is_live(self) -> bool:
        """Running or paused: players can be knocked out, re-enter, take add-ons and sit down."""
        return self.status in ("running", "paused")


class Player(Base):
    """A person who plays in the league. One per phone number across all clubs, so no club_id
    (ADR-0003); a club reaches its players through ClubPlayer."""

    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(16), unique=True)
    # When the player first agreed to the processing of personal data (152-ФЗ).
    consent_given_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ClubPlayer(Base):
    """A player on a club's own list: someone who has been to this club."""

    __tablename__ = "club_players"

    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), primary_key=True, index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Registration(Base):
    """A player signed up for a tournament; checked in once they have come to the club; seated
    once the tournament is running, until they finish with a place."""

    __tablename__ = "registrations"
    __table_args__ = (
        # A player is registered for a tournament at most once.
        UniqueConstraint("tournament_id", "player_id"),
        # One player per seat. Checked at commit, so that the final table can redraw every seat.
        UniqueConstraint(
            "tournament_id", "table_number", "seat_number", deferrable=True, initially="DEFERRED"
        ),
        UniqueConstraint("tournament_id", "finish_order"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id"), index=True)
    tournament_id: Mapped[int] = mapped_column(ForeignKey("tournaments.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checked_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Where the player sits while in the game.
    table_number: Mapped[int | None]
    seat_number: Mapped[int | None]
    # 1 for the first player to finish (be knocked out), and so on; the winner finishes last.
    # A re-entry takes the player back into the game and clears it. See app/game.py for places.
    finish_order: Mapped[int | None]
    reentries: Mapped[int] = mapped_column(default=0)
    addons: Mapped[int] = mapped_column(default=0)
    # One add-on per entry: taken in the current one; a re-entry starts a new entry.
    addon_this_entry: Mapped[bool] = mapped_column(default=False)

    player: Mapped[Player] = relationship()

    @property
    def status(self) -> str:
        if self.finish_order is not None:
            return "out"
        if self.table_number is not None:
            return "in_game"
        return "registered" if self.checked_in_at is None else "checked_in"
