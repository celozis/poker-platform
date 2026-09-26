import os
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import make_url

from tests.clock import FakeClock

if TYPE_CHECKING:
    from app.models import Club

# Tests run against a real PostgreSQL database, never against the dev one.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://poker:poker@localhost:5433/poker_test",
)
# Must be set before app.db is imported, because it creates the engine at import time.
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

BACKEND_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    database_name = make_url(TEST_DATABASE_URL).database or ""
    if not database_name.endswith("_test"):
        # The fixture drops the whole schema, so refuse to touch anything but a test database.
        pytest.exit(f"Refusing to reset non-test database {database_name!r}", returncode=1)

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["configure_logger"] = False
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def empty_tables() -> Iterator[None]:
    yield
    from app import models  # noqa: F401  (registers the tables on Base.metadata)
    from app.db import Base, engine

    table_names = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with engine.begin() as connection:
        connection.execute(text(f"TRUNCATE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture
def client() -> Iterator[TestClient]:
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def clock() -> Iterator[FakeClock]:
    from app.auth import get_now
    from app.main import app

    fake = FakeClock()
    app.dependency_overrides[get_now] = fake
    yield fake
    del app.dependency_overrides[get_now]


@pytest.fixture
def club(client: TestClient, caplog: pytest.LogCaptureFixture, clock: FakeClock) -> "Club":
    """A club whose admin is logged in, with the clock fixed at 2026-09-26 12:00 UTC."""
    from tests.factories import create_admin, create_club
    from tests.login import log_in

    club = create_club(name="Покер-клуб «Обь»")
    create_admin(club, phone="+79130000001")
    log_in(client, caplog, "+79130000001")
    return club
