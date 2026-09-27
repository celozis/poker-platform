from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.clock import FakeClock
from tests.game import knock_out, played_tournament, ready_tournament
from tests.login import log_in
from tests.players import switch_to_another_club

NOVOSIBIRSK = timezone(timedelta(hours=7))


def table(rating: dict[str, Any]) -> list[tuple[int, str, int, int]]:
    return [
        (row["position"], row["player"]["name"], row["points"], row["tournaments"])
        for row in rating["players"]
    ]


def test_the_club_rating_adds_up_the_points_of_the_season(client: TestClient, club: Club) -> None:
    played_tournament(client, club, players=4)  # Гость 04: 10, Гость 03: 4, Гость 02: 2, Гость 01: 0
    played_tournament(client, club, players=2)  # Гость 02: 4, Гость 01: 0

    rating = client.get(f"/api/clubs/{club.id}/rating")

    assert rating.status_code == 200
    assert rating.json()["season"] == {
        "id": "2026-2",
        "name": "2-е полугодие 2026",
        "first_day": "2026-07-01",
        "last_day": "2026-12-31",
    }
    # Equal points share a position; the next player's position counts everyone above.
    assert table(rating.json()) == [
        (1, "Гость 04", 10, 1),
        (2, "Гость 02", 6, 2),
        (3, "Гость 03", 4, 1),
        (4, "Гость 01", 0, 2),
    ]


def test_a_tournament_counts_in_the_season_it_started_in_however_late_it_finishes(
    client: TestClient, club: Club, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    clock.now = datetime(2026, 12, 31, 20, 0, tzinfo=NOVOSIBIRSK)
    log_in(client, caplog, "+79130000001")  # the session of September has expired by now
    url, players = ready_tournament(
        client, club, arrived=2, starts_at="2026-12-31T23:00:00+07:00"
    )
    clock.now = datetime(2026, 12, 31, 23, 10, tzinfo=NOVOSIBIRSK)
    client.post(f"{url}/start")
    clock.now = datetime(2027, 1, 1, 2, 30, tzinfo=NOVOSIBIRSK)
    knock_out(client, url, players[0])

    new_season = client.get(f"/api/clubs/{club.id}/rating").json()
    old_season = client.get(f"/api/clubs/{club.id}/rating?season=2026-2").json()

    assert (new_season["season"]["name"], table(new_season)) == ("1-е полугодие 2027", [])
    assert old_season["season"]["name"] == "2-е полугодие 2026"
    assert table(old_season) == [(1, "Гость 02", 4, 1), (2, "Гость 01", 0, 1)]


def test_the_rating_leads_to_the_season_before_and_back(
    client: TestClient, club: Club
) -> None:
    current = client.get(f"/api/clubs/{club.id}/rating").json()
    before = client.get(f"/api/clubs/{club.id}/rating?season=2026-1").json()

    assert (current["previous_season"], current["next_season"]) == ("2026-1", None)
    assert before["season"]["id"] == "2026-1"
    assert (before["previous_season"], before["next_season"]) == ("2025-2", "2026-2")


def test_there_is_no_rating_of_a_season_that_does_not_exist_or_has_not_begun(
    client: TestClient, club: Club
) -> None:
    for season in ("2026-3", "осень", "2027-1", "0000-1", "0001-1", "9999-2"):
        response = client.get(f"/api/clubs/{club.id}/rating?season={season}")

        assert response.status_code == 404
        assert response.json()["detail"] == "Такого сезона нет"


def test_players_with_equal_points_share_a_position(client: TestClient, club: Club) -> None:
    played_tournament(client, club, players=3)  # Гость 03: 7, Гость 02: 2, Гость 01: 0
    url, players = ready_tournament(client, club, arrived=4)
    client.post(f"{url}/start")
    # Гость 04: 0, Гость 02: 2, Гость 01: 4, Гость 03 wins: 10
    knock_out(client, url, players[3], players[1], players[0])

    assert table(client.get(f"/api/clubs/{club.id}/rating").json()) == [
        (1, "Гость 03", 17, 2),
        (2, "Гость 01", 4, 2),
        (2, "Гость 02", 4, 2),
        (4, "Гость 04", 0, 1),
    ]


def test_a_corrected_place_changes_the_rating_at_once(client: TestClient, club: Club) -> None:
    url, players = played_tournament(client, club, players=4)

    client.put(f"{url}/results/{players[0]['id']}", json={"place": 1})

    assert table(client.get(f"/api/clubs/{club.id}/rating").json()) == [
        (1, "Гость 01", 10, 1),
        (2, "Гость 04", 4, 1),
        (3, "Гость 03", 2, 1),
        (4, "Гость 02", 0, 1),
    ]


def test_only_finished_tournaments_count(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3)
    client.post(f"{url}/start")
    knock_out(client, url, players[0])

    assert client.get(f"/api/clubs/{club.id}/rating").json()["players"] == []


def test_a_club_rating_counts_only_the_clubs_own_tournaments(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    played_tournament(client, club, players=2)
    other_club = switch_to_another_club(client, caplog)
    played_tournament(client, other_club, players=3)

    own = client.get(f"/api/clubs/{other_club.id}/rating").json()
    someone_elses = client.get(f"/api/clubs/{club.id}/rating")

    assert [(name, points) for _, name, points, _ in table(own)] == [
        ("Гость 03", 7),
        ("Гость 02", 2),
        ("Гость 01", 0),
    ]
    assert someone_elses.status_code == 403


def test_the_rating_requires_login(client: TestClient) -> None:
    assert client.get("/api/clubs/1/rating").status_code == 401
