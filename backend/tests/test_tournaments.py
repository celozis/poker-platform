from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.clock import FakeClock
from tests.factories import create_admin, create_club
from tests.game import ready_tournament
from tests.login import log_in
from tests.tournaments import a_break, a_level, a_tournament


def test_admin_creates_a_tournament_from_a_league_template(client: TestClient, club: Club) -> None:
    templates = client.get("/api/blind-templates").json()
    structure = templates[0]["structure"]
    structure[0]["big_blind"] = 250  # change a level
    del structure[1]  # remove a level
    structure.insert(2, a_break(15))  # add a break
    structure.append(a_level(5000, 10000, ante=1000, minutes=15))  # add a level

    created = client.post(
        f"/api/clubs/{club.id}/tournaments",
        json=a_tournament(name="Осенний кубок", structure=structure, addon_at_level=3),
    )

    assert created.status_code == 201
    tournaments = client.get(f"/api/clubs/{club.id}/tournaments").json()
    assert tournaments["past"] == []
    [upcoming] = tournaments["upcoming"]
    assert upcoming == created.json()
    assert upcoming["name"] == "Осенний кубок"
    assert upcoming["starts_at"] == "2026-10-03T12:00:00Z"
    assert upcoming["buy_in"] == 2000
    assert upcoming["starting_stack"] == 20000
    assert upcoming["structure"] == structure
    assert upcoming["reentry_until_level"] == 2
    assert upcoming["addon_at_level"] == 3
    assert upcoming["late_registration_until_level"] == 3
    assert upcoming["status"] == "scheduled"


def names(tournaments: list[dict[str, object]]) -> list[object]:
    return [tournament["name"] for tournament in tournaments]


def test_a_tournament_is_upcoming_until_started_however_late_and_live_while_it_runs(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    saturday, _ = ready_tournament(client, club, arrived=2, name="Субботний")
    url = f"/api/clubs/{club.id}/tournaments"
    for name, starts_at in [("Воскресный", "2026-09-27T12:00:00Z"), ("Пятничный", "2026-10-02T12:00:00Z")]:
        client.post(url, json=a_tournament(name=name, starts_at=starts_at))
    cancelled = client.post(
        url, json=a_tournament(name="Отменённый", starts_at="2026-09-27T15:00:00Z")
    ).json()
    client.post(f"{url}/{cancelled['id']}/cancel")

    before = client.get(url).json()
    client.post(f"{saturday}/start")
    clock.advance(timedelta(days=2))
    after = client.get(url).json()

    assert names(before["live"]) == []
    assert names(before["upcoming"]) == ["Субботний", "Воскресный", "Отменённый", "Пятничный"]
    assert names(after["live"]) == ["Субботний"]
    # Sunday's start time has passed, but nobody has started it yet.
    assert names(after["upcoming"]) == ["Воскресный", "Пятничный"]
    # A cancelled tournament never starts: it is past once its start time has passed.
    assert names(after["past"]) == ["Отменённый"]


def test_admin_edits_a_tournament_before_it_starts(client: TestClient, club: Club) -> None:
    created = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament()).json()
    changes = a_tournament(
        name="Пятничный турбо",
        buy_in=1500,
        structure=[a_level(100, 200, minutes=10), a_level(200, 400, minutes=10)],
        reentry_until_level=None,
        addon_at_level=None,
        late_registration_until_level=1,
    )

    edited = client.put(f"/api/clubs/{club.id}/tournaments/{created['id']}", json=changes)

    assert edited.status_code == 200
    [upcoming] = client.get(f"/api/clubs/{club.id}/tournaments").json()["upcoming"]
    assert upcoming == edited.json()
    assert upcoming["id"] == created["id"]
    assert upcoming["name"] == "Пятничный турбо"
    assert upcoming["buy_in"] == 1500
    assert upcoming["structure"] == changes["structure"]
    assert upcoming["reentry_until_level"] is None
    assert upcoming["addon_at_level"] is None
    assert upcoming["late_registration_until_level"] == 1


def test_admin_cancels_a_tournament_before_it_starts(client: TestClient, club: Club) -> None:
    created = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament()).json()
    cancel_url = f"/api/clubs/{club.id}/tournaments/{created['id']}/cancel"

    cancelled = client.post(cancel_url)
    cancelled_again = client.post(cancel_url)

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled_again.status_code == 200
    # A cancelled tournament stays on the list, marked as cancelled.
    [upcoming] = client.get(f"/api/clubs/{club.id}/tournaments").json()["upcoming"]
    assert upcoming["id"] == created["id"]
    assert upcoming["status"] == "cancelled"


def test_a_started_tournament_can_no_longer_be_edited_or_cancelled(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")

    edited = client.put(url, json=a_tournament(name="Другое название"))
    cancelled = client.post(f"{url}/cancel")

    assert edited.status_code == 409
    assert edited.json()["detail"] == "Турнир уже начался, его нельзя изменить"
    assert cancelled.status_code == 409
    assert cancelled.json()["detail"] == "Турнир уже начался, его нельзя отменить"
    [live] = client.get(f"/api/clubs/{club.id}/tournaments").json()["live"]
    assert (live["name"], live["status"]) == ("Пятничный турнир", "running")


def test_a_tournament_not_started_at_its_time_can_still_be_cancelled(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    url, _ = ready_tournament(client, club, arrived=2)

    clock.advance(timedelta(hours=8))
    cancelled = client.post(f"{url}/cancel")

    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"


def test_a_cancelled_tournament_can_no_longer_be_edited(client: TestClient, club: Club) -> None:
    created = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament()).json()
    url = f"/api/clubs/{club.id}/tournaments/{created['id']}"
    client.post(f"{url}/cancel")

    edited = client.put(url, json=a_tournament(name="Другое название"))

    assert edited.status_code == 409
    assert edited.json()["detail"] == "Турнир отменён, его нельзя изменить"


@pytest.fixture
def other_club_tournament(client: TestClient, caplog: pytest.LogCaptureFixture, club: Club) -> str:
    """URL of a tournament of «Енисей»; afterwards the admin of «Обь» (`club`) is logged in."""
    other_club = create_club(name="Покер-клуб «Енисей»")
    create_admin(other_club, phone="+79130000002")
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000002")
    created = client.post(
        f"/api/clubs/{other_club.id}/tournaments", json=a_tournament(name="Турнир Енисея")
    ).json()
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000001")
    return f"/api/clubs/{other_club.id}/tournaments/{created['id']}"


def test_admin_does_not_see_another_clubs_tournaments(
    client: TestClient, club: Club, other_club_tournament: str
) -> None:
    other_club_list = other_club_tournament.rsplit("/", 1)[0]

    own = client.get(f"/api/clubs/{club.id}/tournaments")
    other = client.get(other_club_list)

    assert own.json() == {"live": [], "upcoming": [], "past": []}
    assert other.status_code == 403
    assert "Енисея" not in other.text


def test_admin_cannot_create_tournaments_in_another_club(
    client: TestClient, club: Club, other_club_tournament: str
) -> None:
    other_club_list = other_club_tournament.rsplit("/", 1)[0]

    response = client.post(other_club_list, json=a_tournament())

    assert response.status_code == 403


def test_admin_cannot_edit_or_cancel_another_clubs_tournament(
    client: TestClient, club: Club, other_club_tournament: str
) -> None:
    tournament_id = other_club_tournament.rsplit("/", 1)[1]
    via_own_club = f"/api/clubs/{club.id}/tournaments/{tournament_id}"

    assert client.put(other_club_tournament, json=a_tournament()).status_code == 403
    assert client.post(f"{other_club_tournament}/cancel").status_code == 403
    # Nor by putting the other club's tournament id under their own club.
    assert client.put(via_own_club, json=a_tournament()).status_code == 404
    assert client.post(f"{via_own_club}/cancel").status_code == 404


def test_tournaments_require_login(client: TestClient) -> None:
    club = create_club()

    assert client.get(f"/api/clubs/{club.id}/tournaments").status_code == 401
    assert client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament()).status_code == 401
    assert client.get("/api/blind-templates").status_code == 401


def test_invalid_tournament_is_rejected_with_a_clear_error(client: TestClient, club: Club) -> None:
    response = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament(addon_at_level=12))

    assert response.status_code == 422
    assert response.json() == {
        "detail": ["Add-on: уровня 12 нет в структуре, в ней уровни с 1 по 3"]
    }
    assert client.get(f"/api/clubs/{club.id}/tournaments").json()["upcoming"] == []


def test_tables_seat_nine_unless_the_admin_says_otherwise(client: TestClient, club: Club) -> None:
    url = f"/api/clubs/{club.id}/tournaments"

    nine = client.post(url, json=a_tournament())
    six_max = client.post(url, json=a_tournament(seats_per_table=6))
    too_few = client.post(url, json=a_tournament(seats_per_table=1))
    too_many = client.post(url, json=a_tournament(seats_per_table=11))

    assert nine.json()["seats_per_table"] == 9
    assert six_max.json()["seats_per_table"] == 6
    for refused in (too_few, too_many):
        assert refused.status_code == 422
        assert refused.json() == {"detail": ["Мест за столом: от 2 до 10"]}


def test_invalid_changes_are_rejected_and_the_tournament_stays_as_it_was(
    client: TestClient, club: Club
) -> None:
    created = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament()).json()

    response = client.put(
        f"/api/clubs/{club.id}/tournaments/{created['id']}",
        json=a_tournament(name="Новое название", starting_stack=0),
    )

    assert response.status_code == 422
    assert response.json() == {"detail": ["Стартовый стек должен быть больше нуля"]}
    assert client.get(f"/api/clubs/{club.id}/tournaments").json()["upcoming"] == [created]


def test_malformed_fields_are_rejected_with_messages_in_russian(
    client: TestClient, club: Club
) -> None:
    payload = a_tournament(buy_in="две тысячи", starts_at="завтра")
    del payload["name"]
    payload["structure"][1]["big_blind"] = 1.5
    payload["structure"][2] = {"kind": "обед", "duration_minutes": 30}

    response = client.post(f"/api/clubs/{club.id}/tournaments", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": [
            "Название: не заполнено",
            "Начало: нужны дата и время",
            "Бай-ин: нужно целое число",
            "Структура блайндов, строка 2, большой блайнд: нужно целое число",
            "Структура блайндов, строка 3: нужен уровень или перерыв",
        ]
    }


def test_every_league_template_makes_a_valid_tournament(client: TestClient, club: Club) -> None:
    templates = client.get("/api/blind-templates").json()

    assert len(templates) >= 1
    for template in templates:
        assert template["name"]
        levels = [item for item in template["structure"] if item["kind"] == "level"]
        assert set(levels[0]) == {"kind", "small_blind", "big_blind", "ante", "duration_minutes"}
        created = client.post(
            f"/api/clubs/{club.id}/tournaments",
            json=a_tournament(
                structure=template["structure"],
                reentry_until_level=len(levels),
                addon_at_level=len(levels),
                late_registration_until_level=len(levels),
            ),
        )
        assert created.status_code == 201, created.json()


def test_a_malformed_tournament_address_is_explained_in_russian(
    client: TestClient, club: Club
) -> None:
    response = client.put(f"/api/clubs/{club.id}/tournaments/пятничный", json=a_tournament())

    assert response.status_code == 422
    assert response.json() == {"detail": ["Номер турнира: нужно целое число"]}
