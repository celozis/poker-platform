import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.factories import create_admin, create_club
from tests.login import log_in


def a_player(**overrides: object) -> dict[str, object]:
    """A new player as the admin panel sends it; override any field."""
    return {"name": "Иван Петров", "phone": "8 (913) 555-12-34", "consent": True} | overrides


def switch_to_another_club(client: TestClient, caplog: pytest.LogCaptureFixture) -> Club:
    """Logs out the admin of «Обь» and logs in the admin of a new club, «Енисей»."""
    other_club = create_club(name="Покер-клуб «Енисей»")
    create_admin(other_club, phone="+79130000002")
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000002")
    return other_club
