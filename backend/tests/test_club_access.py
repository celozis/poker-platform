import pytest
from fastapi.testclient import TestClient

from tests.factories import create_admin, create_club
from tests.login import log_in


def test_admin_sees_their_own_club(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    club = create_club(name="Покер-клуб «Обь»", primary_color="#0B3D91", accent_color="#F2A900")
    create_admin(club, phone="+79130000001")
    log_in(client, caplog, "+79130000001")

    response = client.get(f"/api/clubs/{club.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "Покер-клуб «Обь»"


def test_admin_is_denied_another_clubs_data(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    own_club = create_club(name="Покер-клуб «Обь»")
    other_club = create_club(name="Покер-клуб «Енисей»")
    create_admin(own_club, phone="+79130000001")
    log_in(client, caplog, "+79130000001")

    response = client.get(f"/api/clubs/{other_club.id}")

    assert response.status_code == 403
    assert "Енисей" not in response.text


def test_club_data_requires_login(client: TestClient) -> None:
    club = create_club()

    response = client.get(f"/api/clubs/{club.id}")

    assert response.status_code == 401
