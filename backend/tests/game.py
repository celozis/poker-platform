from typing import Any

from fastapi.testclient import TestClient

from app.models import Club
from tests.players import a_player
from tests.tournaments import a_tournament

# Seven hours after FakeClock's now, so check-in is open.
TONIGHT = "2026-09-26T19:00:00Z"
# How a player pays for a check-in, a re-entry, an add-on or a late seat.
CASH = {"payment_method": "cash"}


def ready_tournament(
    client: TestClient,
    club: Club,
    arrived: int,
    not_arrived: int = 0,
    starts_at: str = TONIGHT,
    **overrides: Any,
) -> tuple[str, list[dict[str, Any]]]:
    """A tournament of `club` tonight with players registered, the first `arrived` checked in.
    The same numbers are the same players in every tournament of the club. Returns the
    tournament's URL and the players in the order they were added."""
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(starts_at=starts_at, **overrides)
    ).json()
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    players = []
    for number in range(1, arrived + not_arrived + 1):
        added = client.post(
            f"/api/clubs/{club.id}/players",
            json=a_player(name=f"Гость {number:02}", phone=f"+7913000{number:04}"),
        ).json()["player"]
        client.post(f"{url}/registrations", json={"player_id": added["id"]})
        if number <= arrived:
            client.post(f"{url}/registrations/{added['id']}/check-in", json=CASH)
        players.append(added)
    return url, players


def knock_out(client: TestClient, url: str, *players: dict[str, Any]) -> None:
    for player in players:
        response = client.post(f"{url}/players/{player['id']}/knock-out")
        assert response.status_code == 200, response.json()


def played_tournament(
    client: TestClient, club: Club, players: int, **overrides: Any
) -> tuple[str, list[dict[str, Any]]]:
    """A tournament of `players` played to the end: knocked out in the order they were added,
    so the last one added wins and the first one added is last."""
    url, added = ready_tournament(client, club, arrived=players, **overrides)
    client.post(f"{url}/start")
    knock_out(client, url, *added[:-1])
    return url, added
