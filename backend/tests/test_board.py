import time
from collections.abc import Iterator
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.models import Club
from tests.clock import FakeClock
from tests.game import CASH, TONIGHT, ready_tournament
from tests.tournaments import a_break, a_level, a_tournament


@pytest.fixture
def hall(client: TestClient) -> Iterator[TestClient]:
    """The browser on the hall's TV: nobody is logged in there."""
    from app.main import app

    with TestClient(app) as anonymous:
        yield anonymous


def board_link(client: TestClient, url: str) -> str:
    """The board's API address for the tournament at `url`, from the code the admin panel gets."""
    tournaments_url, tournament_id = url.rsplit("/", 1)
    listed = client.get(tournaments_url).json()
    [tournament] = [t for tournaments in listed.values() for t in tournaments if t["id"] == int(tournament_id)]
    return f"/api/board/{tournament['board_token']}"


def test_the_board_opens_by_its_link_without_login(
    client: TestClient, club: Club, hall: TestClient
) -> None:
    url, _ = ready_tournament(client, club, arrived=2, name="Пятничный турнир", starting_stack=25000)
    board = hall.get(board_link(client, url))

    assert board.status_code == 200
    assert board.json() == {
        "club": {
            "id": club.id,
            "name": "Покер-клуб «Обь»",
            "logo_url": "/logos/test.svg",
            "primary_color": "#111111",
            "accent_color": "#EEEEEE",
        },
        "name": "Пятничный турнир",
        "starts_at": "2026-09-26T19:00:00Z",
        "status": "scheduled",
        "starting_stack": 25000,
        "structure": [a_level(100, 200), a_level(200, 400), a_break(), a_level(300, 600, ante=75)],
        "clock": None,
        "players_left": 0,
        "players": 0,
        "reentries": 0,
        "average_stack": None,
    }


def test_an_unknown_board_link_is_not_found(hall: TestClient) -> None:
    response = hall.get("/api/board/000000000000")

    assert response.status_code == 404
    assert response.json() == {"detail": "Табло не найдено"}



def started(client: TestClient, club: Club, arrived: int, **overrides: Any) -> tuple[str, str]:
    """A started tournament of `club` with `arrived` players at the tables, and its board link."""
    url, _ = ready_tournament(client, club, arrived=arrived, **overrides)
    assert client.post(f"{url}/start").status_code == 200
    return url, board_link(client, url)


def test_a_knock_out_changes_the_players_left_and_the_average_stack(
    client: TestClient, club: Club, hall: TestClient
) -> None:
    url, board_url = started(client, club, arrived=3, starting_stack=20000)
    [first, *_] = client.get(f"{url}/game").json()["in_game"]
    before = hall.get(board_url).json()

    client.post(f"{url}/players/{first['player']['id']}/knock-out")

    after = hall.get(board_url).json()
    assert (before["players_left"], before["players"], before["average_stack"]) == (3, 3, 20000)
    assert (after["players_left"], after["players"], after["average_stack"]) == (2, 3, 30000)


def test_the_board_counts_reentries_and_addons_into_the_average_stack(
    client: TestClient, club: Club, hall: TestClient
) -> None:
    url, board_url = started(client, club, arrived=3, starting_stack=20000, addon_stack=30000)
    first, second, _ = client.get(f"{url}/game").json()["in_game"]
    client.post(f"{url}/players/{first['player']['id']}/knock-out")
    client.post(f"{url}/players/{first['player']['id']}/reentry", json=CASH)
    client.post(f"{url}/next-level")  # the add-on is taken on level 2
    client.post(f"{url}/players/{second['player']['id']}/addon", json=CASH)

    board = hall.get(board_url).json()

    assert (board["players_left"], board["players"], board["reentries"]) == (3, 3, 1)
    # Four starting stacks of 20 000 and an add-on of 30 000 among three players.
    assert board["average_stack"] == 36667


def receive_within(board: WebSocketTestSession, seconds: float = 1.0) -> Any:
    """The next state the board is sent; fails instead of hanging when none comes in time."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(board.receive_json).result(timeout=seconds)
    finally:
        pool.shutdown(wait=False)


def test_the_board_hears_of_a_pause_in_under_a_second(
    client: TestClient, club: Club, hall: TestClient
) -> None:
    url, board_url = started(client, club, arrived=2)

    with hall.websocket_connect(f"{board_url}/ws") as board:
        now = receive_within(board)
        paused_at = time.monotonic()
        client.post(f"{url}/pause")
        paused = receive_within(board)
        delay = time.monotonic() - paused_at

    assert (now["status"], now["clock"]["running"]) == ("running", True)
    assert (paused["status"], paused["clock"]["running"]) == ("paused", False)
    assert delay < 1


def test_the_board_hears_of_the_start_a_level_change_and_a_knock_out(
    client: TestClient, club: Club, hall: TestClient
) -> None:
    url, _ = ready_tournament(client, club, arrived=3)

    with hall.websocket_connect(f"{board_link(client, url)}/ws") as board:
        before = receive_within(board)
        client.post(f"{url}/start")
        on_start = receive_within(board)
        client.post(f"{url}/next-level")
        on_next_level = receive_within(board)
        [first, *_] = client.get(f"{url}/game").json()["in_game"]
        client.post(f"{url}/players/{first['player']['id']}/knock-out")
        on_knock_out = receive_within(board)

    assert (before["status"], before["players_left"]) == ("scheduled", 0)
    assert (on_start["status"], on_start["clock"]["item"], on_start["players_left"]) == ("running", 0, 3)
    assert on_next_level["clock"]["item"] == 1
    assert (on_knock_out["players_left"], on_knock_out["average_stack"]) == (2, 30000)


def test_a_board_that_reconnects_gets_what_it_missed(
    client: TestClient, club: Club, hall: TestClient
) -> None:
    url, board_url = started(client, club, arrived=2)
    with hall.websocket_connect(f"{board_url}/ws") as board:
        receive_within(board)

    # Changes made while the board is off line.
    client.post(f"{url}/next-level")
    client.post(f"{url}/pause")

    with hall.websocket_connect(f"{board_url}/ws") as board:
        now = receive_within(board)
    assert (now["status"], now["clock"]["item"], now["clock"]["running"]) == ("paused", 1, False)


def test_an_unknown_board_cannot_be_watched(hall: TestClient) -> None:
    # Accepted and then closed, so that a browser also sees why: a connection refused before
    # it is accepted reaches the browser as a plain network failure.
    with hall.websocket_connect("/api/board/000000000000/ws") as board:
        with pytest.raises(WebSocketDisconnect) as refused:
            receive_within(board)

    assert (refused.value.code, refused.value.reason) == (4404, "Табло не найдено")


def test_the_board_hears_of_changes_before_the_start(
    client: TestClient, club: Club, hall: TestClient
) -> None:
    url, _ = ready_tournament(client, club, arrived=2, name="Пятничный турнир")

    with hall.websocket_connect(f"{board_link(client, url)}/ws") as board:
        receive_within(board)
        client.put(url, json=a_tournament(starts_at=TONIGHT, name="Субботний турнир"))
        edited = receive_within(board)
        client.post(f"{url}/cancel")
        cancelled = receive_within(board)

    assert edited["name"] == "Субботний турнир"
    assert cancelled["status"] == "cancelled"


def test_the_board_and_the_admin_panel_get_the_same_time_to_the_millisecond(
    client: TestClient, club: Club, hall: TestClient, clock: FakeClock
) -> None:
    url, board_url = started(client, club, arrived=2)

    clock.advance(timedelta(seconds=10, milliseconds=250))

    assert hall.get(board_url).json()["clock"]["seconds_left"] == 1189.75
    assert client.get(f"{url}/game").json()["clock"]["seconds_left"] == 1189.75
