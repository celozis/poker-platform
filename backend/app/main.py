from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_session

app = FastAPI(title="Poker Platform API")


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
