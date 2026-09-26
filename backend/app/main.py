import logging
from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import auth, blind_templates, clubs, game, players, registrations, tournaments
from app.db import get_session
from app.validation_errors import russian_validation_errors

# Uvicorn only configures its own loggers; without this, INFO messages from the app
# (such as the prototype's login codes) would never reach the backend log.
_app_logger = logging.getLogger("app")
_app_logger.setLevel(logging.INFO)
if not _app_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    _app_logger.addHandler(_handler)

app = FastAPI(title="Poker Platform API")
app.add_exception_handler(RequestValidationError, russian_validation_errors)
app.include_router(auth.router)
app.include_router(clubs.router)
app.include_router(tournaments.router)
app.include_router(blind_templates.router)
app.include_router(players.router)
app.include_router(registrations.router)
app.include_router(game.router)


class Health(BaseModel):
    api: Literal["ok"]
    database: Literal["ok", "unavailable"]


@app.get("/api/health")
def health(session: Annotated[Session, Depends(get_session)]) -> Health:
    # The API answers even when the database is down, so the caller can tell the two apart.
    try:
        session.execute(text("SELECT 1"))
        return Health(api="ok", database="ok")
    except SQLAlchemyError:
        return Health(api="ok", database="unavailable")
