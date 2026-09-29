"""The admin panel hears at once that a tournament has changed, whoever changed it: in the admin
panel, or a player in the Telegram bot, which runs as a process of its own (ADR-0010). The
signal comes over a WebSocket; the panel then reads what it shows afresh."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession
from starlette.websockets import WebSocketDisconnect

from app.models import Club
from tests.bot import BotChat, go_through_the_bot
from tests.clock import FakeClock
from tests.game import CASH, ready_tournament
from tests.players import switch_to_another_club
from tests.tournaments import a_tournament


def receive_within(changes: WebSocketTestSession, seconds: float = 1.0) -> str:
    """The next signal; fails instead of hanging when none comes in time."""
    pool = ThreadPoolExecutor(max_workers=1)
    try:
        return pool.submit(changes.receive_text).result(timeout=seconds)
    finally:
        pool.shutdown(wait=False)


@pytest.fixture
def chat(clock: FakeClock) -> BotChat:
    return BotChat(clock)


def test_the_admin_panel_hears_at_once_that_a_player_signed_up_in_the_bot(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир")
    ).json()
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    go_through_the_bot(chat)
    chat.send("/schedule")

    with client.websocket_connect(f"{url}/ws") as changes:
        chat.press("Записаться: 3.10 Субботний турнир")
        assert receive_within(changes) == "changed"


def test_the_admin_panel_hears_at_once_that_a_player_dropped_out_in_the_bot(
    chat: BotChat, client: TestClient, club: Club
) -> None:
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир")
    ).json()
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    go_through_the_bot(chat)
    chat.send("/schedule")
    chat.press("Записаться: 3.10 Субботний турнир")

    with client.websocket_connect(f"{url}/ws") as changes:
        chat.press("Отменить запись: 3.10 Субботний турнир")
        assert receive_within(changes) == "changed"


def test_only_the_clubs_own_admin_may_watch_its_tournament(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    tournament = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament()).json()
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    switch_to_another_club(client, caplog)

    with client.websocket_connect(f"{url}/ws") as changes:
        with pytest.raises(WebSocketDisconnect) as refused:
            receive_within(changes)
    assert (refused.value.code, refused.value.reason) == (4403, "Нет доступа к турниру")

    client.post("/api/auth/logout")
    with client.websocket_connect(f"{url}/ws") as changes:
        with pytest.raises(WebSocketDisconnect) as refused:
            receive_within(changes)
    assert refused.value.code == 4403


def test_another_admin_screen_hears_of_every_registration_change_made_in_the_admin_panel(
    client: TestClient, club: Club
) -> None:
    url, (player,) = ready_tournament(client, club, arrived=0, not_arrived=1)
    registration = f"{url}/registrations/{player['id']}"
    client.delete(registration)

    with client.websocket_connect(f"{url}/ws") as changes:
        client.post(f"{url}/registrations", json={"player_id": player["id"]})
        assert receive_within(changes) == "changed"
        client.post(f"{registration}/check-in", json=CASH)
        assert receive_within(changes) == "changed"
        client.delete(f"{registration}/check-in")
        assert receive_within(changes) == "changed"
        client.delete(registration)
        assert receive_within(changes) == "changed"
