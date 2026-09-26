import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.factories import create_admin, create_club
from tests.login import log_in
from tests.players import a_player, switch_to_another_club


def test_admin_adds_a_player_to_the_club(client: TestClient, club: Club) -> None:
    added = client.post(f"/api/clubs/{club.id}/players", json=a_player())

    assert added.status_code == 201
    assert added.json()["outcome"] == "created"
    player = added.json()["player"]
    assert player["name"] == "Иван Петров"
    assert player["phone"] == "+79135551234"
    assert client.get(f"/api/clubs/{club.id}/players").json() == [player]


def test_a_player_is_not_added_without_consent_to_data_processing(
    client: TestClient, club: Club
) -> None:
    response = client.post(f"/api/clubs/{club.id}/players", json=a_player(consent=False))

    assert response.status_code == 422
    assert response.json() == {
        "detail": ["Без согласия на обработку персональных данных игрока завести нельзя"]
    }
    assert client.get(f"/api/clubs/{club.id}/players").json() == []


def test_a_player_needs_a_name_and_a_russian_phone_number(client: TestClient, club: Club) -> None:
    response = client.post(
        f"/api/clubs/{club.id}/players", json=a_player(name="  ", phone="555-12-34")
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            "Укажите имя игрока",
            "Телефон: нужен российский номер из 11 цифр, например +7 913 555-12-34",
        ]
    }
    assert client.get(f"/api/clubs/{club.id}/players").json() == []


def test_a_league_player_entered_again_is_brought_into_the_club_not_duplicated(
    client: TestClient, caplog: pytest.LogCaptureFixture, club: Club
) -> None:
    original = client.post(f"/api/clubs/{club.id}/players", json=a_player()).json()["player"]
    other_club = switch_to_another_club(client, caplog)

    # The same phone typed differently, and the name as the other club's admin heard it.
    added = client.post(
        f"/api/clubs/{other_club.id}/players",
        json=a_player(name="Ваня Петров", phone="+7 913 555 12 34"),
    )
    added_again = client.post(f"/api/clubs/{other_club.id}/players", json=a_player())

    assert added.status_code == 200
    assert added.json() == {"player": original, "outcome": "added_to_club"}
    assert added_again.status_code == 200
    assert added_again.json() == {"player": original, "outcome": "already_in_club"}
    assert client.get(f"/api/clubs/{other_club.id}/players").json() == [original]


def test_admin_finds_club_players_by_name_or_phone(
    client: TestClient, caplog: pytest.LogCaptureFixture, club: Club
) -> None:
    other_club = switch_to_another_club(client, caplog)
    client.post(
        f"/api/clubs/{other_club.id}/players",
        json=a_player(name="Иван Смирнов", phone="+79137770001"),
    )
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000001")
    for name, phone in [
        ("Иван Петров", "+79135551234"),
        ("Мария Иванова", "+79131110002"),
        ("Сергей Никитин", "+79131110003"),
    ]:
        client.post(f"/api/clubs/{club.id}/players", json=a_player(name=name, phone=phone))

    def found(query: str) -> list[str]:
        response = client.get(f"/api/clubs/{club.id}/players", params={"q": query})
        return [player["name"] for player in response.json()]

    # Only this club's players, in name order; another club's Иван Смирнов is not found.
    assert found("иван") == ["Иван Петров", "Мария Иванова"]
    assert found("8 913 555") == ["Иван Петров"]
    assert found("111-00-03") == ["Сергей Никитин"]
    assert found("Анна") == []
    assert found("%") == []
    assert found("8") == []  # a lone 8 is a digit to look for, not "any number starting with +7"
    assert found("  ") == ["Иван Петров", "Мария Иванова", "Сергей Никитин"]


def test_admin_cannot_see_or_add_players_of_another_club(
    client: TestClient, caplog: pytest.LogCaptureFixture, club: Club
) -> None:
    client.post(f"/api/clubs/{club.id}/players", json=a_player(name="Игрок Оби"))
    switch_to_another_club(client, caplog)

    listed = client.get(f"/api/clubs/{club.id}/players")
    added = client.post(f"/api/clubs/{club.id}/players", json=a_player(phone="+79137770001"))

    assert listed.status_code == 403
    assert "Игрок Оби" not in listed.text
    assert added.status_code == 403


def test_players_require_login(client: TestClient) -> None:
    club = create_club()

    assert client.get(f"/api/clubs/{club.id}/players").status_code == 401
    assert client.post(f"/api/clubs/{club.id}/players", json=a_player()).status_code == 401


def test_malformed_player_fields_are_explained_in_russian(client: TestClient, club: Club) -> None:
    response = client.post(
        f"/api/clubs/{club.id}/players", json={"name": "Иван Петров", "consent": "может быть"}
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            "Телефон: не заполнено",
            "Согласие на обработку данных: нужно да или нет",
        ]
    }
