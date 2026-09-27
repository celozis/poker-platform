from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.game import knock_out, played_tournament, ready_tournament
from tests.players import switch_to_another_club


def standings(results: dict[str, Any]) -> list[tuple[int, str, int]]:
    return [(r["place"], r["player"]["name"], r["points"]) for r in results["results"]]


def test_once_finished_every_player_has_a_place_and_points(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3, not_arrived=1)
    client.post(f"{url}/start")
    knock_out(client, url, players[0], players[2])

    results = client.get(f"{url}/results")

    assert results.status_code == 200
    assert results.json() == {
        "status": "finished",
        "results": [
            {"place": 1, "player": players[1], "points": 7, "reentries": 0, "addons": 0},
            {"place": 2, "player": players[2], "points": 2, "reentries": 0, "addons": 0},
            {"place": 3, "player": players[0], "points": 0, "reentries": 0, "addons": 0},
        ],
    }


def test_a_player_who_re_entered_has_one_result_and_is_counted_once(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=4)
    client.post(f"{url}/start")
    knock_out(client, url, players[0])
    client.post(f"{url}/players/{players[0]['id']}/reentry")
    knock_out(client, url, players[1], players[0], players[2])

    results = client.get(f"{url}/results").json()

    # Four players, five entries: the points are those of a four-player field.
    assert standings(results) == [
        (1, "Гость 04", 10),
        (2, "Гость 03", 4),
        (3, "Гость 01", 2),
        (4, "Гость 02", 0),
    ]
    assert [r["reentries"] for r in results["results"]] == [0, 0, 1, 0]


def test_a_tournament_has_no_results_until_it_is_finished(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3)
    client.post(f"{url}/start")
    knock_out(client, url, players[0])

    assert client.get(f"{url}/results").json() == {"status": "running", "results": []}


def test_the_game_shows_the_points_of_a_finished_tournament(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")

    knock_out(client, url, players[0])

    out = client.get(f"{url}/game").json()["out"]
    assert [(f["player"]["name"], f["place"], f["points"]) for f in out] == [
        ("Гость 02", 1, 4),
        ("Гость 01", 2, 0),
    ]


def test_a_corrected_place_moves_the_players_in_between_and_recounts_points(
    client: TestClient, club: Club
) -> None:
    url, players = played_tournament(client, club, players=4)

    corrected = client.put(f"{url}/results/{players[0]['id']}", json={"place": 2})

    assert corrected.status_code == 200
    # Гость 01 was knocked out later than marked: the two who were above move down one place.
    assert standings(corrected.json()) == [
        (1, "Гость 04", 10),
        (2, "Гость 01", 4),
        (3, "Гость 03", 2),
        (4, "Гость 02", 0),
    ]
    assert client.get(f"{url}/results").json() == corrected.json()
    game_places = [(f["player"]["name"], f["place"]) for f in client.get(f"{url}/game").json()["out"]]
    assert game_places == [("Гость 04", 1), ("Гость 01", 2), ("Гость 03", 3), ("Гость 02", 4)]


def test_a_place_is_one_of_the_places_of_the_tournament(client: TestClient, club: Club) -> None:
    url, players = played_tournament(client, club, players=4)
    before = client.get(f"{url}/results").json()

    for place in (0, 5, -1):
        response = client.put(f"{url}/results/{players[0]['id']}", json={"place": place})

        assert response.status_code == 422
        assert response.json()["detail"] == ["Место: от 1 до 4"]
    assert client.get(f"{url}/results").json() == before


def test_places_are_corrected_only_in_a_finished_tournament(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3)
    client.post(f"{url}/start")
    knock_out(client, url, players[0])

    response = client.put(f"{url}/results/{players[0]['id']}", json={"place": 2})

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "Места исправляют после завершения турнира; пока он идёт, отмените выбывание"
    )


def test_only_a_player_who_played_has_a_place_to_correct(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2, not_arrived=1)
    client.post(f"{url}/start")
    knock_out(client, url, players[0])

    response = client.put(f"{url}/results/{players[2]['id']}", json={"place": 1})

    assert response.status_code == 404
    assert response.json()["detail"] == "Игрок не играл в этом турнире"


def test_admin_sees_and_corrects_only_their_own_clubs_results(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    url, players = played_tournament(client, club, players=4)
    switch_to_another_club(client, caplog)

    seen = client.get(f"{url}/results")
    corrected = client.put(f"{url}/results/{players[0]['id']}", json={"place": 1})

    assert (seen.status_code, corrected.status_code) == (403, 403)
