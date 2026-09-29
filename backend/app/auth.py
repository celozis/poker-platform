"""Admin login by phone number and a one-time code, without passwords."""

import hashlib
import hmac
import logging
import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Admin, AdminSession, LoginCode
from app.schemas import AdminOut, ClubOut, Me

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth")

CODE_TTL = timedelta(minutes=5)
RESEND_INTERVAL = timedelta(minutes=1)
MAX_FAILED_ATTEMPTS = 5
SESSION_TTL = timedelta(days=7)
SESSION_COOKIE = "admin_session"
# Shared by set_cookie and delete_cookie: a cookie is only deleted if these match.
SESSION_COOKIE_SCOPE: dict[str, Any] = {"path": "/api", "httponly": True, "samesite": "strict"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def get_clock() -> Callable[[], datetime]:
    """What tells the time; tests put a fake clock here. A request asks it once (Now), a hall
    board's connection every time it sends the board (app/board.py)."""
    return _utc_now


Clock = Annotated[Callable[[], datetime], Depends(get_clock)]


def get_now(clock: Clock) -> datetime:
    return clock()


DbSession = Annotated[Session, Depends(get_session)]
Now = Annotated[datetime, Depends(get_now)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


def normalize_phone(raw: str) -> str | None:
    """Brings a Russian number typed as "8 913 ...", "+7 (913) ..." etc. to "+7XXXXXXXXXX"."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    return None


def hash_secret(secret: str) -> str:
    """What the server keeps of a login code or a session token: never the secret itself."""
    return hashlib.sha256(secret.encode()).hexdigest()


class CodeRequest(BaseModel):
    phone: str


class CodeVerification(BaseModel):
    phone: str
    code: str


# What a login code opens: the admin panel or a player's web cabinet (app/cabinet.py). An admin
# who also plays gets a code for each, and one does not open the other.
LoginPurpose = Literal["admin", "cabinet"]
_CODE_MESSAGES: dict[LoginPurpose, str] = {
    "admin": "Код входа для %s: %s",
    "cabinet": "Код входа в кабинет игрока для %s: %s",
}


def send_login_code(session: Session, purpose: LoginPurpose, phone: str, now: datetime) -> None:
    """Sends a new code to the phone, unless one went less than RESEND_INTERVAL ago. The caller
    has checked that the phone is someone's who may log in."""
    pending = session.get(LoginCode, {"purpose": purpose, "phone": phone}, with_for_update=True)
    if pending is not None and now - pending.sent_at < RESEND_INTERVAL:
        # A new code would reset the wrong-attempt counter, so resending is throttled.
        return
    code = f"{secrets.randbelow(1_000_000):06d}"
    session.merge(
        LoginCode(
            purpose=purpose,
            phone=phone,
            code_hash=hash_secret(code),
            sent_at=now,
            expires_at=now + CODE_TTL,
            failed_attempts=0,
        )
    )
    session.commit()
    # Prototype stand-in for an SMS gateway: the code is read from the backend log.
    logger.info(_CODE_MESSAGES[purpose], phone, code)


def take_login_code(
    session: Session, purpose: LoginPurpose, phone: str, code: str, now: datetime
) -> bool:
    """Whether `code` is the one sent to the phone and still valid. A right code is used up with
    the caller's commit; a wrong one counts against the code, committed at once."""
    # Locked so that parallel wrong guesses cannot slip past MAX_FAILED_ATTEMPTS.
    login_code = session.get(
        LoginCode, {"purpose": purpose, "phone": phone}, with_for_update=True
    )
    if login_code is None or login_code.expires_at <= now:
        return False
    if not hmac.compare_digest(login_code.code_hash, hash_secret(code.strip())):
        # A six-digit code is guessable, so it burns after a few wrong tries.
        login_code.failed_attempts += 1
        if login_code.failed_attempts >= MAX_FAILED_ATTEMPTS:
            session.delete(login_code)
        session.commit()
        return False
    session.delete(login_code)
    return True


def new_session_token() -> tuple[str, str]:
    """A random token for the session cookie, and its hash, which is all the server keeps."""
    token = secrets.token_urlsafe(32)
    return token, hash_secret(token)


@router.post("/request-code", status_code=status.HTTP_204_NO_CONTENT)
def request_code(body: CodeRequest, session: DbSession, now: Now) -> None:
    phone = normalize_phone(body.phone)
    if phone is None or session.scalar(select(Admin.id).where(Admin.phone == phone)) is None:
        # Unknown numbers get the same answer, so the endpoint does not reveal who is an admin.
        return
    send_login_code(session, "admin", phone, now)


@router.post("/verify-code", status_code=status.HTTP_204_NO_CONTENT)
def verify_code(body: CodeVerification, response: Response, session: DbSession, now: Now) -> None:
    phone = normalize_phone(body.phone)
    admin = session.scalar(select(Admin).where(Admin.phone == phone)) if phone else None
    if admin is None or not take_login_code(session, "admin", admin.phone, body.code, now):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный или просроченный код")
    token, token_hash = new_session_token()
    session.add(AdminSession(token_hash=token_hash, admin_id=admin.id, expires_at=now + SESSION_TTL))
    session.commit()
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), **SESSION_COOKIE_SCOPE
    )


def current_admin(session: DbSession, now: Now, token: SessionToken = None) -> Admin:
    stored = session.get(AdminSession, hash_secret(token)) if token else None
    if stored is None or stored.expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход")
    return stored.admin


CurrentAdmin = Annotated[Admin, Depends(current_admin)]


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, session: DbSession, token: SessionToken = None) -> None:
    if token:
        session.execute(delete(AdminSession).where(AdminSession.token_hash == hash_secret(token)))
        session.commit()
    response.delete_cookie(SESSION_COOKIE, **SESSION_COOKIE_SCOPE)


@router.get("/me")
def me(admin: CurrentAdmin) -> Me:
    return Me(admin=AdminOut.model_validate(admin), club=ClubOut.model_validate(admin.club))
