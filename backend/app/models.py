from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String
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
    status: Mapped[str] = mapped_column(String(20), default="scheduled")

    def has_started(self, now: datetime) -> bool:
        # There is no "start" action yet, so a tournament starts at its start time.
        return self.starts_at <= now
