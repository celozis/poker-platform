from collections import Counter
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.clock import FakeClock
from tests.game import ready_tournament
from tests.login import log_in
from tests.players import switch_to_another_club


def table_sizes(game: dict[str, Any]) -> list[int]:
    return sorted(Counter(seated["table"] for seated in game["in_game"]).values(), reverse=True)


def test_start_seats_every_arrived_player_evenly_and_starts_the_clock(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=12, not_arrived=1)

    started = client.post(f"{url}/start")

    assert started.status_code == 200
    game = started.json()
    assert game["status"] == "running"
    assert table_sizes(game) == [6, 6]
    assert {seated["player"]["id"] for seated in game["in_game"]} == {p["id"] for p in players[:12]}
    assert game["waiting"] == [{"player": players[12], "status": "registered"}]
    assert game["clock"] == {"running": True, "item": 0, "seconds_left": 20 * 60}
    assert client.get(f"{url}/game").json() == game


def test_a_tournament_needs_two_arrived_players_to_start(client: TestClient, club: Club) -> None:
    url, _ = ready_tournament(client, club, arrived=1, not_arrived=3)

    response = client.post(f"{url}/start")

    assert response.status_code == 409
    assert response.json()["detail"] == "Для старта нужны хотя бы два пришедших игрока"
    assert client.get(f"{url}/game").json()["status"] == "scheduled"


def test_a_running_tournament_is_not_started_again(client: TestClient, club: Club) -> None:
    url, _ = ready_tournament(client, club, arrived=2)
    first = client.post(f"{url}/start").json()

    again = client.post(f"{url}/start")

    assert again.status_code == 409
    assert again.json()["detail"] == "Турнир уже идёт"
    assert client.get(f"{url}/game").json()["in_game"] == first["in_game"]


def clock_of(client: TestClient, url: str) -> dict[str, Any]:
    clock: dict[str, Any] = client.get(f"{url}/game").json()["clock"]
    return clock


def test_the_blind_clock_moves_on_to_the_next_level_by_itself(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    # Level 1 and level 2 of 20 minutes, a 10-minute break, level 3.
    url, _ = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")

    clock.advance(timedelta(minutes=7, seconds=30))
    assert clock_of(client, url) == {"running": True, "item": 0, "seconds_left": 12 * 60 + 30}
    clock.advance(timedelta(minutes=35))
    assert clock_of(client, url) == {"running": True, "item": 2, "seconds_left": 7 * 60 + 30}


def test_admin_pauses_and_resumes_the_clock(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    url, _ = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")
    clock.advance(timedelta(minutes=5))

    paused = client.post(f"{url}/pause").json()
    clock.advance(timedelta(hours=1))
    still = client.get(f"{url}/game").json()
    resumed = client.post(f"{url}/resume").json()
    clock.advance(timedelta(minutes=1))

    assert (paused["status"], paused["clock"]) == (
        "paused",
        {"running": False, "item": 0, "seconds_left": 15 * 60},
    )
    assert still["clock"] == paused["clock"]
    assert (resumed["status"], resumed["clock"]["running"]) == ("running", True)
    assert clock_of(client, url)["seconds_left"] == 14 * 60


def test_pausing_twice_or_resuming_a_running_clock_is_refused(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")

    resumed = client.post(f"{url}/resume")
    client.post(f"{url}/pause")
    paused_again = client.post(f"{url}/pause")

    assert (resumed.status_code, resumed.json()["detail"]) == (409, "Турнир не на паузе")
    assert (paused_again.status_code, paused_again.json()["detail"]) == (
        409,
        "Турнир уже на паузе",
    )


def test_admin_switches_the_level_forward_and_back(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    url, _ = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")
    clock.advance(timedelta(minutes=5))

    back_at_first = client.post(f"{url}/previous-level")
    forward = client.post(f"{url}/next-level").json()
    to_break = client.post(f"{url}/next-level").json()
    to_last = client.post(f"{url}/next-level").json()
    past_last = client.post(f"{url}/next-level")
    back = client.post(f"{url}/previous-level").json()

    assert (back_at_first.status_code, back_at_first.json()["detail"]) == (
        409,
        "Это первый уровень структуры",
    )
    assert forward["clock"] == {"running": True, "item": 1, "seconds_left": 20 * 60}
    assert to_break["clock"]["item"] == 2
    assert to_last["clock"]["item"] == 3
    assert (past_last.status_code, past_last.json()["detail"]) == (
        409,
        "Это последний уровень структуры",
    )
    assert back["clock"] == {"running": True, "item": 2, "seconds_left": 10 * 60}


def test_the_clock_cannot_be_touched_before_the_start(client: TestClient, club: Club) -> None:
    url, _ = ready_tournament(client, club, arrived=2)

    for action in ("pause", "resume", "next-level", "previous-level"):
        response = client.post(f"{url}/{action}")
        assert (response.status_code, response.json()["detail"]) == (409, "Турнир ещё не начался")


def places(game: dict[str, Any]) -> list[tuple[str, int]]:
    return [(finished["player"]["name"], finished["place"]) for finished in game["out"]]


def test_a_knocked_out_player_gets_the_place_they_finished_in(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=4)
    client.post(f"{url}/start")

    first = client.post(f"{url}/players/{players[2]['id']}/knock-out")
    second = client.post(f"{url}/players/{players[0]['id']}/knock-out").json()

    assert first.status_code == 200
    assert places(first.json()) == [("Гость 03", 4)]
    assert places(second) == [("Гость 01", 3), ("Гость 03", 4)]
    assert {seated["player"]["id"] for seated in second["in_game"]} == {
        players[1]["id"],
        players[3]["id"],
    }
    assert second["status"] == "running"


def test_a_reentry_or_a_late_player_after_a_knock_out_moves_that_place_down(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=4, not_arrived=1)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")  # 4th of 4
    client.post(f"{url}/players/{players[1]['id']}/knock-out")  # 3rd of 4

    reentered = client.post(f"{url}/players/{players[0]['id']}/reentry").json()
    late = client.post(f"{url}/players/{players[4]['id']}/seat").json()

    # Гость 01 is back in the game, so Гость 02 finished first of the four.
    assert places(reentered) == [("Гость 02", 4)]
    # A fifth player has joined: whoever finished first is now fifth.
    assert places(late) == [("Гость 02", 5)]


def test_the_last_player_standing_wins_and_the_tournament_is_finished(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=3)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")

    finished = client.post(f"{url}/players/{players[2]['id']}/knock-out").json()

    assert finished["status"] == "finished"
    assert places(finished) == [("Гость 02", 1), ("Гость 03", 2), ("Гость 01", 3)]
    assert finished["in_game"] == []
    assert finished["clock"]["running"] is False
    [past] = client.get(f"/api/clubs/{club.id}/tournaments").json()["past"]
    assert past["status"] == "finished"


def test_a_finished_tournament_cannot_be_started_again_or_played_on(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")

    started = client.post(f"{url}/start")
    resumed = client.post(f"{url}/resume")
    knocked_out = client.post(f"{url}/players/{players[1]['id']}/knock-out")

    assert (started.status_code, started.json()["detail"]) == (
        409,
        "Турнир уже завершён, его нельзя снова запустить",
    )
    for refused in (resumed, knocked_out):
        assert (refused.status_code, refused.json()["detail"]) == (409, "Турнир завершён")
    assert client.get(f"{url}/game").json()["status"] == "finished"


def test_only_a_player_in_the_game_can_be_knocked_out(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3, not_arrived=1)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")

    again = client.post(f"{url}/players/{players[0]['id']}/knock-out")
    not_seated = client.post(f"{url}/players/{players[3]['id']}/knock-out")
    unknown = client.post(f"{url}/players/999/knock-out")

    assert (again.status_code, again.json()["detail"]) == (409, "Игрок Гость 01 уже выбыл")
    assert (not_seated.status_code, not_seated.json()["detail"]) == (409, "Игрок Гость 04 не в игре")
    assert (unknown.status_code, unknown.json()["detail"]) == (
        404,
        "Игрок не зарегистрирован на этот турнир",
    )


def test_players_that_fit_at_one_table_are_drawn_for_the_final_table(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=10)
    started = client.post(f"{url}/start").json()
    assert table_sizes(started) == [5, 5]

    final = client.post(f"{url}/players/{players[0]['id']}/knock-out").json()

    assert table_sizes(final) == [9]
    assert {seated["table"] for seated in final["in_game"]} == {1}
    assert len({seated["seat"] for seated in final["in_game"]}) == 9
    assert final["suggested_move"] is None


def seated(game: dict[str, Any], player: dict[str, Any]) -> dict[str, Any]:
    """The player's place at the tables; fails if they are not in the game."""
    seats: list[dict[str, Any]] = [s for s in game["in_game"] if s["player"]["id"] == player["id"]]
    [seat] = seats
    return seat


def test_a_knocked_out_player_re_enters_up_to_the_reentry_level_and_its_break(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    # Re-entry until level 2; the break after level 2 runs from 40 to 50 minutes.
    url, players = ready_tournament(client, club, arrived=4, reentry_until_level=2)
    client.post(f"{url}/start")
    player = players[0]

    clock.advance(timedelta(minutes=45))
    client.post(f"{url}/players/{player['id']}/knock-out")
    on_break = client.post(f"{url}/players/{player['id']}/reentry")
    clock.advance(timedelta(minutes=6))
    client.post(f"{url}/players/{player['id']}/knock-out")
    too_late = client.post(f"{url}/players/{player['id']}/reentry")

    assert on_break.status_code == 200
    assert seated(on_break.json(), player)["reentries"] == 1
    assert on_break.json()["out"] == []
    assert (too_late.status_code, too_late.json()["detail"]) == (
        409,
        "Re-entry закрыт: он был до уровня 2",
    )
    assert places(client.get(f"{url}/game").json()) == [("Гость 01", 4)]


def test_a_player_still_in_the_game_does_not_re_enter(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3)
    client.post(f"{url}/start")

    response = client.post(f"{url}/players/{players[0]['id']}/reentry")

    assert (response.status_code, response.json()["detail"]) == (409, "Игрок Гость 01 ещё в игре")


def test_there_is_no_reentry_in_a_tournament_without_it(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3, reentry_until_level=None)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")

    response = client.post(f"{url}/players/{players[0]['id']}/reentry")

    assert (response.status_code, response.json()["detail"]) == (409, "В этом турнире нет re-entry")


def test_addon_is_taken_on_its_level_once_per_entry(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3, addon_at_level=2, reentry_until_level=2)
    client.post(f"{url}/start")
    player_url = f"{url}/players/{players[0]['id']}"

    too_early = client.post(f"{player_url}/addon")
    client.post(f"{url}/next-level")
    taken = client.post(f"{player_url}/addon")
    twice = client.post(f"{player_url}/addon")
    client.post(f"{player_url}/knock-out")
    client.post(f"{player_url}/reentry")
    after_reentry = client.post(f"{player_url}/addon")

    assert (too_early.status_code, too_early.json()["detail"]) == (
        409,
        "Add-on берут на уровне 2 и в перерыве после него",
    )
    assert taken.status_code == 200
    assert seated(taken.json(), players[0])["addons"] == 1
    assert (twice.status_code, twice.json()["detail"]) == (
        409,
        "Игрок Гость 01 уже взял add-on",
    )
    assert seated(after_reentry.json(), players[0])["addons"] == 2


def test_a_reentry_made_before_the_addon_level_gives_no_second_addon(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=3, addon_at_level=2, reentry_until_level=2)
    client.post(f"{url}/start")
    player_url = f"{url}/players/{players[0]['id']}"
    client.post(f"{player_url}/knock-out")
    client.post(f"{player_url}/reentry")
    client.post(f"{url}/next-level")

    first = client.post(f"{player_url}/addon")
    second = client.post(f"{player_url}/addon")

    assert first.status_code == 200
    assert (second.status_code, second.json()["detail"]) == (409, "Игрок Гость 01 уже взял add-on")
    assert seated(client.get(f"{url}/game").json(), players[0])["addons"] == 1


def test_addon_needs_a_player_in_the_game_and_a_tournament_that_offers_it(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=3, addon_at_level=None)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")

    none_offered = client.post(f"{url}/players/{players[1]['id']}/addon")
    out = client.post(f"{url}/players/{players[0]['id']}/addon")

    assert (none_offered.status_code, none_offered.json()["detail"]) == (
        409,
        "В этом турнире нет add-on",
    )
    assert (out.status_code, out.json()["detail"]) == (409, "Игрок Гость 01 уже выбыл")


def test_a_late_player_is_registered_and_seated_while_late_registration_is_open(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    # 7 players at 6-seat tables sit 4 and 3; the newcomer goes to the smaller table.
    url, players = ready_tournament(
        client, club, arrived=7, not_arrived=1, seats_per_table=6, late_registration_until_level=1
    )
    started = client.post(f"{url}/start").json()
    smaller = min((1, 2), key=lambda t: sum(s["table"] == t for s in started["in_game"]))
    newcomer = client.post(
        f"/api/clubs/{club.id}/players",
        json={"name": "Новичок", "phone": "+79139999999", "consent": True},
    ).json()["player"]

    registered = client.post(f"{url}/registrations", json={"player_id": newcomer["id"]})
    seated_newcomer = client.post(f"{url}/players/{newcomer['id']}/seat").json()
    seated_late = client.post(f"{url}/players/{players[7]['id']}/seat").json()
    clock.advance(timedelta(minutes=20))
    registered_too_late = client.post(f"{url}/registrations", json={"player_id": players[0]["id"]})

    assert registered.status_code == 201
    assert seated(seated_newcomer, newcomer)["table"] == smaller
    assert seated_late["waiting"] == []
    assert table_sizes(seated_late) == [5, 4]
    assert registered_too_late.json()["detail"] == "Поздняя регистрация закрыта: она шла до уровня 1"
    assert [r["status"] for r in client.get(f"{url}/registrations").json()["registrations"]] == [
        "in_game"
    ] * 9


def test_late_seating_is_refused_once_late_registration_closes(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    url, players = ready_tournament(
        client, club, arrived=2, not_arrived=1, late_registration_until_level=1
    )
    client.post(f"{url}/start")

    already = client.post(f"{url}/players/{players[0]['id']}/seat")
    clock.advance(timedelta(minutes=20))
    too_late = client.post(f"{url}/players/{players[2]['id']}/seat")

    assert (already.status_code, already.json()["detail"]) == (409, "Игрок Гость 01 уже в игре")
    assert (too_late.status_code, too_late.json()["detail"]) == (
        409,
        "Поздняя регистрация закрыта: она шла до уровня 1",
    )


def test_after_knock_outs_the_system_suggests_a_move_and_the_admin_makes_it(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=18)
    started = client.post(f"{url}/start").json()
    table_one = [s["player"]["id"] for s in started["in_game"] if s["table"] == 1]
    assert started["suggested_move"] is None

    for player_id in table_one[:3]:
        game = client.post(f"{url}/players/{player_id}/knock-out").json()

    # 6 players at table 1 and 9 at table 2: one moves from table 2 to table 1.
    move = game["suggested_move"]
    assert (move["from_table"], move["to_table"]) == (2, 1)
    moved = client.post(
        f"{url}/players/{move['player']['id']}/move",
        json={"table": move["to_table"], "seat": move["to_seat"]},
    )

    assert moved.status_code == 200
    assert seated(moved.json(), move["player"])["table"] == 1
    assert table_sizes(moved.json()) == [8, 7]
    assert moved.json()["suggested_move"] is None


def test_a_player_moves_only_to_a_free_seat_that_exists(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3)
    game = client.post(f"{url}/start").json()
    taken = seated(game, players[1])

    to_taken = client.post(
        f"{url}/players/{players[0]['id']}/move", json={"table": taken["table"], "seat": taken["seat"]}
    )
    to_nowhere = client.post(f"{url}/players/{players[0]['id']}/move", json={"table": 1, "seat": 10})
    to_no_table = client.post(f"{url}/players/{players[0]['id']}/move", json={"table": 57, "seat": 1})
    to_new_table = client.post(f"{url}/players/{players[0]['id']}/move", json={"table": 2, "seat": 1})

    assert (to_taken.status_code, to_taken.json()["detail"]) == (
        409,
        f"Стол {taken['table']}, место {taken['seat']} занято",
    )
    assert (to_nowhere.status_code, to_nowhere.json()["detail"]) == (
        409,
        "За столом места с 1 по 9",
    )
    assert (to_no_table.status_code, to_no_table.json()["detail"]) == (
        409,
        "Стола 57 нет: пересадить можно за стол 1 или открыть стол 2",
    )
    assert seated(to_new_table.json(), players[0])["table"] == 2


GAME_ACTIONS = [
    ("GET", "game"),
    ("POST", "start"),
    ("POST", "pause"),
    ("POST", "resume"),
    ("POST", "next-level"),
    ("POST", "previous-level"),
    ("POST", "players/{player}/knock-out"),
    ("POST", "players/{player}/reentry"),
    ("POST", "players/{player}/addon"),
    ("POST", "players/{player}/seat"),
    ("POST", "players/{player}/move"),
]


def call(client: TestClient, url: str, method: str, action: str, player_id: int) -> int:
    path = f"{url}/{action.format(player=player_id)}"
    body = {"table": 1, "seat": 1} if action.endswith("move") else None
    return client.request(method, path, json=body).status_code


def test_admin_cannot_run_another_clubs_tournament(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    url, players = ready_tournament(client, club, arrived=3)
    client.post(f"{url}/start")
    other_club = switch_to_another_club(client, caplog)
    # The tournament of «Обь» under the address of «Енисей» is not found either.
    own_address = url.replace(f"/api/clubs/{club.id}/", f"/api/clubs/{other_club.id}/")

    for method, action in GAME_ACTIONS:
        assert call(client, url, method, action, players[0]["id"]) == 403, action
        assert call(client, own_address, method, action, players[0]["id"]) == 404, action

    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000001")
    game = client.get(f"{url}/game").json()
    assert (game["status"], len(game["in_game"])) == ("running", 3)


def test_running_a_tournament_requires_login(client: TestClient) -> None:
    for method, action in GAME_ACTIONS:
        assert call(client, "/api/clubs/1/tournaments/1", method, action, 1) == 401, action


def test_a_malformed_move_is_explained_in_russian(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")

    response = client.post(f"{url}/players/{players[0]['id']}/move", json={"table": "второй"})

    assert response.status_code == 422
    assert response.json() == {"detail": ["Стол: нужно целое число", "Место: не заполнено"]}
