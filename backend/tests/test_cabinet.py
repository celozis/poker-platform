from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.bot import BotChat, go_through_the_bot
from tests.clock import FakeClock
from tests.game import TONIGHT, CASH, knock_out, played_tournament, ready_tournament
from tests.login import code_from_log, log_in_to_cabinet, request_code
from tests.players import a_player, switch_to_another_club
from tests.tournaments import NEXT_WEEK, a_tournament


def cabinet(client: TestClient) -> dict[str, Any]:
    response = client.get("/api/cabinet")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


def test_a_player_logs_in_with_the_code_from_the_log_and_sees_their_profile(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    client.post(
        f"/api/clubs/{club.id}/players",
        json=a_player(name="Иван Петров", phone="8 (913) 555-12-34"),
    )
    caplog.set_level("INFO")

    requested = client.post("/api/cabinet/request-code", json={"phone": "+7 913 555 12 34"})
    assert requested.status_code == 204
    code = code_from_log(caplog, "+79135551234")
    verified = client.post("/api/cabinet/verify-code", json={"phone": "89135551234", "code": code})
    assert verified.status_code == 204

    shown = cabinet(client)
    assert shown["player"] == {
        "name": "Иван Петров",
        "phone": "+79135551234",
        "telegram_linked": False,
    }
    assert [c["club"]["name"] for c in shown["clubs"]] == ["Покер-клуб «Обь»"]


def test_a_player_who_came_through_the_telegram_bot_sees_it_linked(
    client: TestClient, club: Club, clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    go_through_the_bot(BotChat(clock))

    log_in_to_cabinet(client, caplog, "+79135551234")

    assert cabinet(client)["player"] == {
        "name": "Мария Иванова",
        "phone": "+79135551234",
        "telegram_linked": True,
    }


def test_the_player_sees_their_position_and_points_in_each_of_their_clubs_this_season(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    played_tournament(client, club, players=4)  # Гость 04: 10, Гость 03: 4, Гость 02: 2, Гость 01: 0
    played_tournament(client, club, players=2)  # Гость 02: 4, Гость 01: 0
    other_club = switch_to_another_club(client, caplog)
    client.post(
        f"/api/clubs/{other_club.id}/players",
        json=a_player(name="Гость 02", phone="+79130000002"),
    )

    log_in_to_cabinet(client, caplog, "+79130000002")

    shown = cabinet(client)
    assert shown["season"]["name"] == "2-е полугодие 2026"
    assert [(c["club"]["name"], c["rating"]) for c in shown["clubs"]] == [
        # Гость 04 has more points; Гость 03 fewer.
        ("Покер-клуб «Обь»", {"position": 2, "points": 6, "tournaments": 2}),
        # On the club's list, but no finished tournament of the club this season.
        ("Покер-клуб «Енисей»", None),
    ]


def test_the_player_sees_the_tournaments_they_played_in_every_club_the_latest_first(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    url, (guest_1, guest_2, guest_3) = ready_tournament(
        client, club, arrived=3, name="Пятничный турнир", starts_at="2026-09-26T13:00:00Z"
    )
    client.post(f"{url}/start")
    client.post(f"{url}/next-level")  # level 2: re-entry and add-on
    client.post(f"{url}/players/{guest_2['id']}/addon", json=CASH)
    knock_out(client, url, guest_2)
    client.post(f"{url}/players/{guest_2['id']}/reentry", json=CASH)
    knock_out(client, url, guest_1, guest_3)
    # Signed up for next week's, which has not been played yet.
    ready_tournament(client, club, arrived=0, not_arrived=2, starts_at=NEXT_WEEK)
    other_club = switch_to_another_club(client, caplog)
    played_tournament(
        client, other_club, players=2, name="Енисей Open", starts_at="2026-09-26T20:00:00Z"
    )

    log_in_to_cabinet(client, caplog, "+79130000002")

    assert cabinet(client)["history"] == [
        {
            "starts_at": "2026-09-26T20:00:00Z",
            "tournament": "Енисей Open",
            "club": "Покер-клуб «Енисей»",
            "place": 1,
            "players": 2,
            "points": 4,
            "reentries": 0,
            "addons": 0,
        },
        {
            "starts_at": "2026-09-26T13:00:00Z",
            "tournament": "Пятничный турнир",
            "club": "Покер-клуб «Обь»",
            # Out once, back by the re-entry, and the last one standing: 10 × (√3 − 1) ≈ 7.
            "place": 1,
            "players": 3,
            "points": 7,
            "reentries": 1,
            "addons": 1,
        },
    ]


def test_the_player_sees_the_coming_tournaments_of_each_of_their_clubs_marked_if_signed_up(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    ready_tournament(
        client, club, arrived=0, not_arrived=2, name="Пятничный турнир", starts_at=NEXT_WEEK
    )
    client.post(
        f"/api/clubs/{club.id}/tournaments",
        json=a_tournament(name="Субботний турнир", starts_at="2026-10-04T19:00:00+07:00"),
    )
    cancelled = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Отменённый турнир")
    ).json()
    client.post(f"/api/clubs/{club.id}/tournaments/{cancelled['id']}/cancel")
    # Going on, and late registration is open until level 3.
    url, _ = ready_tournament(client, club, arrived=2, name="Вечерний турнир", starts_at=TONIGHT)
    client.post(f"{url}/start")
    other_club = switch_to_another_club(client, caplog)
    client.post(
        f"/api/clubs/{other_club.id}/players",
        json=a_player(name="Гость 02", phone="+79130000002"),
    )
    client.post(
        f"/api/clubs/{other_club.id}/tournaments",
        json=a_tournament(name="Енисей Open", buy_in=3000),
    )

    log_in_to_cabinet(client, caplog, "+79130000002")

    assert [(c["club"]["name"], c["schedule"]) for c in cabinet(client)["clubs"]] == [
        (
            "Покер-клуб «Обь»",
            [
                {
                    "name": "Вечерний турнир",
                    "starts_at": "2026-09-26T19:00:00Z",
                    "buy_in": 2000,
                    "going_on": True,
                    "registered": True,
                },
                {
                    "name": "Пятничный турнир",
                    "starts_at": "2026-10-03T12:00:00Z",
                    "buy_in": 2000,
                    "going_on": False,
                    "registered": True,
                },
                {
                    "name": "Субботний турнир",
                    "starts_at": "2026-10-04T12:00:00Z",
                    "buy_in": 2000,
                    "going_on": False,
                    "registered": False,
                },
            ],
        ),
        (
            "Покер-клуб «Енисей»",
            [
                {
                    "name": "Енисей Open",
                    "starts_at": "2026-10-03T12:00:00Z",
                    "buy_in": 3000,
                    "going_on": False,
                    "registered": False,
                },
            ],
        ),
    ]


def test_the_cabinet_needs_the_players_own_login_not_an_admins(
    client: TestClient, club: Club
) -> None:
    # The club fixture has logged its admin in to the admin panel.
    response = client.get("/api/cabinet")

    assert response.status_code == 401


def test_a_players_login_opens_none_of_the_club_data_the_admin_panel_shows(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    played_tournament(client, club, players=2)
    client.post("/api/auth/logout")

    log_in_to_cabinet(client, caplog, "+79130000002")

    for club_data in ("players", "rating", "tournaments"):
        response = client.get(f"/api/clubs/{club.id}/{club_data}")
        assert response.status_code == 401, club_data
        assert "Гость 01" not in response.text


def test_the_admin_panels_code_does_not_open_the_cabinet_of_an_admin_who_also_plays(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture, clock: FakeClock
) -> None:
    # The club's admin, +7 913 000-00-01, plays in the club as Гость 01.
    played_tournament(client, club, players=2)
    clock.advance(timedelta(minutes=1))  # a new admin code may be sent
    admin_code = request_code(client, caplog, "+79130000001")

    verified = client.post(
        "/api/cabinet/verify-code", json={"phone": "+79130000001", "code": admin_code}
    )

    assert verified.status_code == 401
    assert client.get("/api/cabinet").status_code == 401


def test_a_phone_the_league_does_not_know_gets_no_code(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("INFO")

    requested = client.post("/api/cabinet/request-code", json={"phone": "+79139999999"})

    assert requested.status_code == 204
    assert not any("+79139999999" in record.getMessage() for record in caplog.records)


def test_a_logged_out_players_session_no_longer_works(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    played_tournament(client, club, players=2)
    log_in_to_cabinet(client, caplog, "+79130000002")
    token = client.cookies["player_session"]

    assert client.post("/api/cabinet/logout").status_code == 204

    assert client.get("/api/cabinet").status_code == 401
    # Even a copy of the old cookie is useless: the session is gone on the server.
    client.cookies.set("player_session", token)
    assert client.get("/api/cabinet").status_code == 401


def test_a_player_sees_nothing_of_another_players_even_asking_for_them_by_id(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    _, (guest_1, _) = played_tournament(client, club, players=2)  # Гость 02 wins, Гость 01 is 2nd
    client.post("/api/auth/logout")

    log_in_to_cabinet(client, caplog, "+79130000002")
    shown = client.get("/api/cabinet", params={"player_id": guest_1["id"]})

    assert shown.status_code == 200
    assert shown.json()["player"]["name"] == "Гость 02"
    assert [(p["place"], p["points"]) for p in shown.json()["history"]] == [(1, 4)]
    assert shown.json()["clubs"][0]["rating"] == {"position": 1, "points": 4, "tournaments": 1}
    assert "Гость 01" not in shown.text
    assert client.get(f"/api/cabinet/{guest_1['id']}").status_code in (404, 405)
