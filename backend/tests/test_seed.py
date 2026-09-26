import re

import pytest
from fastapi.testclient import TestClient

from app.seed import seed
from tests.login import log_in

# The seeded admins' phone numbers, as documented in CONTEXT.md.
SEEDED_ADMIN_PHONES = ["+79990000001", "+79990000002"]
HEX_COLOR = re.compile(r"^#[0-9A-Fa-f]{6}$")


def club_of_admin(client: TestClient, caplog: pytest.LogCaptureFixture, phone: str) -> dict[str, object]:
    log_in(client, caplog, phone)
    club: dict[str, object] = client.get("/api/auth/me").json()["club"]
    client.post("/api/auth/logout")
    return club


def test_seed_creates_two_branded_clubs_with_an_admin_each(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    seed()

    first, second = (club_of_admin(client, caplog, phone) for phone in SEEDED_ADMIN_PHONES)

    assert first["id"] != second["id"]
    for club in (first, second):
        assert club["name"]
        assert str(club["logo_url"]).startswith("/logos/")
        assert HEX_COLOR.match(str(club["primary_color"]))
        assert HEX_COLOR.match(str(club["accent_color"]))


def test_seed_can_be_run_again(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    seed()
    first_run = [club_of_admin(client, caplog, phone) for phone in SEEDED_ADMIN_PHONES]

    seed()

    assert [club_of_admin(client, caplog, phone) for phone in SEEDED_ADMIN_PHONES] == first_run
