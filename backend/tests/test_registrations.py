from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.clock import FakeClock
from tests.factories import create_club
from tests.login import log_in
from tests.players import a_player, switch_to_another_club
from tests.tournaments import a_tournament


def add_player(client: TestClient, club: Club, name: str, phone: str) -> dict[str, Any]:
    response = client.post(f"/api/clubs/{club.id}/players", json=a_player(name=name, phone=phone))
    player: dict[str, Any] = response.json()["player"]
    return player


def create_tournament(client: TestClient, club: Club, **overrides: Any) -> str:
    """Creates a tournament of `club` and returns the URL of its registrations."""
    created = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament(**overrides)).json()
    return f"/api/clubs/{club.id}/tournaments/{created['id']}/registrations"


def test_admin_registers_club_players_for_an_upcoming_tournament(
    client: TestClient, club: Club
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    maria = add_player(client, club, "Мария Иванова", "+79131110002")
    registrations = create_tournament(client, club)

    first = client.post(registrations, json={"player_id": maria["id"]})
    second = client.post(registrations, json={"player_id": ivan["id"]})

    assert first.status_code == 201
    assert first.json() == {"player": maria, "status": "registered"}
    assert second.status_code == 201
    listed = client.get(registrations).json()
    assert listed["registrations"] == [
        {"player": ivan, "status": "registered"},
        {"player": maria, "status": "registered"},
    ]


def test_a_player_cannot_be_registered_for_the_same_tournament_twice(
    client: TestClient, club: Club
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    registrations = create_tournament(client, club)
    client.post(registrations, json={"player_id": ivan["id"]})

    again = client.post(registrations, json={"player_id": ivan["id"]})

    assert again.status_code == 409
    assert again.json()["detail"] == "Иван Петров уже зарегистрирован на этот турнир"
    assert client.get(registrations).json()["registrations"] == [
        {"player": ivan, "status": "registered"}
    ]


def test_only_the_clubs_own_players_can_be_registered(client: TestClient, club: Club) -> None:
    registrations = create_tournament(client, club)

    response = client.post(registrations, json={"player_id": 12345})

    assert response.status_code == 404
    assert response.json()["detail"] == "Игрок не найден в клубе"


def test_registration_is_open_only_until_the_tournament_starts(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    maria = add_player(client, club, "Мария Иванова", "+79131110002")
    registrations = create_tournament(client, club, starts_at="2026-09-26T19:00:00Z")
    client.post(registrations, json={"player_id": ivan["id"]})
    before = client.get(registrations).json()

    clock.advance(timedelta(hours=7))
    late = client.post(registrations, json={"player_id": maria["id"]})

    assert before["registration_open"] is True
    assert late.status_code == 409
    assert late.json()["detail"] == "Турнир уже начался, регистрация закрыта"
    after = client.get(registrations).json()
    assert after["registration_open"] is False
    assert after["registrations"] == [{"player": ivan, "status": "registered"}]


def test_a_cancelled_tournament_takes_no_registrations(client: TestClient, club: Club) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    registrations = create_tournament(client, club)
    client.post(registrations.replace("/registrations", "/cancel"))

    response = client.post(registrations, json={"player_id": ivan["id"]})

    assert response.status_code == 409
    assert response.json()["detail"] == "Турнир отменён, регистрация закрыта"
    assert client.get(registrations).json()["registration_open"] is False


def test_admin_cancels_a_registration_before_the_tournament_starts(
    client: TestClient, club: Club
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    maria = add_player(client, club, "Мария Иванова", "+79131110002")
    registrations = create_tournament(client, club)
    client.post(registrations, json={"player_id": ivan["id"]})
    client.post(registrations, json={"player_id": maria["id"]})

    cancelled = client.delete(f"{registrations}/{ivan['id']}")
    cancelled_again = client.delete(f"{registrations}/{ivan['id']}")

    assert cancelled.status_code == 204
    assert cancelled_again.status_code == 404
    assert cancelled_again.json()["detail"] == "Игрок не зарегистрирован на этот турнир"
    assert client.get(registrations).json()["registrations"] == [
        {"player": maria, "status": "registered"}
    ]
    # The player can sign up again later.
    assert client.post(registrations, json={"player_id": ivan["id"]}).status_code == 201


def test_a_registration_cannot_be_cancelled_once_the_tournament_has_started(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    registrations = create_tournament(client, club, starts_at="2026-09-26T19:00:00Z")
    client.post(registrations, json={"player_id": ivan["id"]})

    clock.advance(timedelta(hours=7))
    response = client.delete(f"{registrations}/{ivan['id']}")

    assert response.status_code == 409
    assert response.json()["detail"] == "Турнир уже начался, регистрация закрыта"
    assert client.get(registrations).json()["registrations"] == [
        {"player": ivan, "status": "registered"}
    ]


def test_check_in_is_open_from_12_hours_before_to_12_hours_after_the_start(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    maria = add_player(client, club, "Мария Иванова", "+79131110002")
    # Starts in 31 hours, at 2026-09-27 19:00 UTC.
    registrations = create_tournament(client, club, starts_at="2026-09-27T19:00:00Z")
    client.post(registrations, json={"player_id": ivan["id"]})
    client.post(registrations, json={"player_id": maria["id"]})

    too_early = client.post(f"{registrations}/{ivan['id']}/check-in")
    early_listing = client.get(registrations).json()
    clock.advance(timedelta(hours=19))  # 12 hours before the start
    checked_in = client.post(f"{registrations}/{ivan['id']}/check-in")
    checked_in_again = client.post(f"{registrations}/{ivan['id']}/check-in")
    clock.advance(timedelta(hours=24))  # 12 hours after the start
    latecomer = client.post(f"{registrations}/{maria['id']}/check-in")
    clock.advance(timedelta(minutes=1))
    too_late = client.post(f"{registrations}/{maria['id']}/check-in")

    assert too_early.status_code == 409
    assert too_early.json()["detail"] == "Отметка о приходе откроется за 12 часов до начала турнира"
    assert early_listing["check_in_open"] is False
    assert checked_in.status_code == 200
    assert checked_in.json() == {"player": ivan, "status": "checked_in"}
    assert checked_in_again.json() == {"player": ivan, "status": "checked_in"}
    assert latecomer.json() == {"player": maria, "status": "checked_in"}
    assert too_late.status_code == 409
    assert too_late.json()["detail"] == "Отметка о приходе закрыта: турнир начался больше 12 часов назад"
    listing = client.get(registrations).json()
    assert listing["check_in_open"] is False
    assert listing["registrations"] == [
        {"player": ivan, "status": "checked_in"},
        {"player": maria, "status": "checked_in"},
    ]


def test_admin_undoes_a_check_in_made_by_mistake(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    registrations = create_tournament(client, club, starts_at="2026-09-26T19:00:00Z")
    client.post(registrations, json={"player_id": ivan["id"]})
    client.post(f"{registrations}/{ivan['id']}/check-in")

    undone = client.delete(f"{registrations}/{ivan['id']}/check-in")

    assert undone.status_code == 200
    assert undone.json() == {"player": ivan, "status": "registered"}
    listing = client.get(registrations).json()
    assert listing["check_in_open"] is True
    assert listing["registrations"] == [{"player": ivan, "status": "registered"}]


def test_nobody_checks_in_to_a_cancelled_tournament(client: TestClient, club: Club) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    registrations = create_tournament(client, club, starts_at="2026-09-26T19:00:00Z")
    client.post(registrations, json={"player_id": ivan["id"]})
    client.post(registrations.replace("/registrations", "/cancel"))

    response = client.post(f"{registrations}/{ivan['id']}/check-in")

    assert response.status_code == 409
    assert response.json()["detail"] == "Турнир отменён"
    assert client.get(registrations).json()["check_in_open"] is False


def test_admin_cannot_touch_another_clubs_registrations(
    client: TestClient, caplog: pytest.LogCaptureFixture, club: Club
) -> None:
    ivan = add_player(client, club, "Иван Петров", "+79135551234")
    registrations = create_tournament(client, club, starts_at="2026-09-26T19:00:00Z")
    client.post(registrations, json={"player_id": ivan["id"]})
    other_club = switch_to_another_club(client, caplog)
    stranger = add_player(client, other_club, "Пётр Енисейский", "+79137770001")
    own_registrations = create_tournament(client, other_club, starts_at="2026-09-26T19:00:00Z")
    tournament_id = registrations.split("/")[5]
    via_own_club = f"/api/clubs/{other_club.id}/tournaments/{tournament_id}/registrations"

    listed = client.get(registrations)
    assert listed.status_code == 403
    assert "Иван" not in listed.text
    assert client.post(registrations, json={"player_id": stranger["id"]}).status_code == 403
    assert client.delete(f"{registrations}/{ivan['id']}").status_code == 403
    assert client.post(f"{registrations}/{ivan['id']}/check-in").status_code == 403
    assert client.delete(f"{registrations}/{ivan['id']}/check-in").status_code == 403
    # Nor through their own club's URL with the other club's tournament id.
    assert client.get(via_own_club).status_code == 404
    assert client.delete(f"{via_own_club}/{ivan['id']}").status_code == 404
    assert client.post(f"{via_own_club}/{ivan['id']}/check-in").status_code == 404
    assert client.delete(f"{via_own_club}/{ivan['id']}/check-in").status_code == 404
    # Nor by registering the other club's player for their own tournament.
    assert client.post(own_registrations, json={"player_id": ivan["id"]}).status_code == 404

    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000001")
    assert client.get(registrations).json()["registrations"] == [
        {"player": ivan, "status": "registered"}
    ]


def test_registrations_require_login(client: TestClient) -> None:
    club = create_club()
    registrations = f"/api/clubs/{club.id}/tournaments/1/registrations"

    assert client.get(registrations).status_code == 401
    assert client.post(registrations, json={"player_id": 1}).status_code == 401
    assert client.delete(f"{registrations}/1").status_code == 401
    assert client.post(f"{registrations}/1/check-in").status_code == 401
    assert client.delete(f"{registrations}/1/check-in").status_code == 401


def test_a_malformed_player_address_is_explained_in_russian(client: TestClient, club: Club) -> None:
    registrations = create_tournament(client, club)

    response = client.post(f"{registrations}/иван/check-in")

    assert response.status_code == 422
    assert response.json() == {"detail": ["Номер игрока: нужно целое число"]}
