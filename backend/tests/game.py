from typing import Any

from fastapi.testclient import TestClient

from app.models import Club
from tests.players import a_player
from tests.tournaments import a_tournament

# Seven hours after FakeClock's now, so check-in is open.
TONIGHT = "2026-09-26T19:00:00Z"


def ready_tournament(
    client: TestClient, club: Club, arrived: int, not_arrived: int = 0, **overrides: Any
) -> tuple[str, list[dict[str, Any]]]:
    """A tournament of `club` tonight with players registered, the first `arrived` checked in.
    Returns the tournament's URL and the players in the order they were added."""
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(starts_at=TONIGHT, **overrides)
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
            client.post(f"{url}/registrations/{added['id']}/check-in")
        players.append(added)
    return url, players
