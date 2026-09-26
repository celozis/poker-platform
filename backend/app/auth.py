"""Admin login by phone number and a one-time code, without passwords."""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

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


def get_now() -> datetime:
    return datetime.now(UTC)


DbSession = Annotated[Session, Depends(get_session)]
Now = Annotated[datetime, Depends(get_now)]
SessionToken = Annotated[str | None, Cookie(alias=SESSION_COOKIE)]


def normalize_phone(raw: str) -> str | None:
    """Brings a Russian number typed as "8 913 ...", "+7 (913) ..." etc. to "+7XXXXXXXXXX"."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits[0] in "78":
        return "+7" + digits[1:]
    return None


def _hash(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


class CodeRequest(BaseModel):
    phone: str


class CodeVerification(BaseModel):
    phone: str
    code: str


@router.post("/request-code", status_code=status.HTTP_204_NO_CONTENT)
def request_code(body: CodeRequest, session: DbSession, now: Now) -> None:
    phone = normalize_phone(body.phone)
    if phone is None or session.scalar(select(Admin.id).where(Admin.phone == phone)) is None:
        # Unknown numbers get the same answer, so the endpoint does not reveal who is an admin.
        return
    pending = session.get(LoginCode, phone, with_for_update=True)
    if pending is not None and now - pending.sent_at < RESEND_INTERVAL:
        # A new code would reset the wrong-attempt counter, so resending is throttled.
        return
    code = f"{secrets.randbelow(1_000_000):06d}"
    session.merge(
        LoginCode(
            phone=phone,
            code_hash=_hash(code),
            sent_at=now,
            expires_at=now + CODE_TTL,
            failed_attempts=0,
        )
    )
    session.commit()
    # Prototype stand-in for an SMS gateway: the admin reads the code from the backend log.
    logger.info("Код входа для %s: %s", phone, code)


@router.post("/verify-code", status_code=status.HTTP_204_NO_CONTENT)
def verify_code(body: CodeVerification, response: Response, session: DbSession, now: Now) -> None:
    phone = normalize_phone(body.phone)
    # Locked so that parallel wrong guesses cannot slip past MAX_FAILED_ATTEMPTS.
    login_code = session.get(LoginCode, phone, with_for_update=True) if phone else None
    admin = session.scalar(select(Admin).where(Admin.phone == phone)) if phone else None
    invalid_code = HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный или просроченный код")
    if login_code is None or admin is None or login_code.expires_at <= now:
        raise invalid_code
    if not hmac.compare_digest(login_code.code_hash, _hash(body.code.strip())):
        # A six-digit code is guessable, so it burns after a few wrong tries.
        login_code.failed_attempts += 1
        if login_code.failed_attempts >= MAX_FAILED_ATTEMPTS:
            session.delete(login_code)
        session.commit()
        raise invalid_code

    session.delete(login_code)
    token = secrets.token_urlsafe(32)
    session.add(AdminSession(token_hash=_hash(token), admin_id=admin.id, expires_at=now + SESSION_TTL))
    session.commit()
    response.set_cookie(
        SESSION_COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), **SESSION_COOKIE_SCOPE
    )


def current_admin(session: DbSession, now: Now, token: SessionToken = None) -> Admin:
    stored = session.get(AdminSession, _hash(token)) if token else None
    if stored is None or stored.expires_at <= now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Требуется вход")
    return stored.admin


CurrentAdmin = Annotated[Admin, Depends(current_admin)]


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response, session: DbSession, token: SessionToken = None) -> None:
    if token:
        session.execute(delete(AdminSession).where(AdminSession.token_hash == _hash(token)))
        session.commit()
    response.delete_cookie(SESSION_COOKIE, **SESSION_COOKIE_SCOPE)


@router.get("/me")
def me(admin: CurrentAdmin) -> Me:
    return Me(admin=AdminOut.model_validate(admin), club=ClubOut.model_validate(admin.club))
