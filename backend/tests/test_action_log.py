"""The tournament's action log: who did what, when and to which player, so that the club can
settle a dispute. Every action writes its own entry; the log only shows them, the latest first."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.bot import BotChat, go_through_the_bot
from tests.clock import FakeClock
from tests.game import CASH, TONIGHT, played_tournament, ready_tournament
from tests.players import a_player, switch_to_another_club
from tests.tournaments import a_break, a_level, a_tournament

PLAYER = "игрок"
ADMIN = "Администратор"


def entries(client: TestClient, url: str, **params: Any) -> list[tuple[str, str, str | None, str]]:
    """The log as the admin reads it: action, who did it, the player it was done to, details."""
    response = client.get(f"{url}/log", params=params)
    assert response.status_code == 200, response.json()
    return [
        (
            entry["action"],
            PLAYER if entry["admin"] is None else entry["admin"]["name"],
            None if entry["player"] is None else entry["player"]["name"],
            entry["details"],
        )
        for entry in response.json()
    ]


def test_a_registration_by_the_admin_is_logged_with_who_whom_and_when(
    client: TestClient, club: Club
) -> None:
    tournament = client.post(f"/api/clubs/{club.id}/tournaments", json=a_tournament()).json()
    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    player = client.post(f"/api/clubs/{club.id}/players", json=a_player()).json()["player"]

    client.post(f"{url}/registrations", json={"player_id": player["id"]})

    assert entries(client, url) == [("registered", ADMIN, "Иван Петров", "")]
    assert client.get(f"{url}/log").json()[0]["created_at"] == "2026-09-26T12:00:00Z"


def test_signing_up_and_dropping_out_in_the_bot_is_logged_as_done_by_the_player(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    tournament = client.post(
        f"/api/clubs/{club.id}/tournaments", json=a_tournament(name="Субботний турнир")
    ).json()
    chat = BotChat(clock)
    go_through_the_bot(chat)
    chat.send("/schedule")

    chat.press("Записаться: 3.10 Субботний турнир")
    chat.press("Отменить запись: 3.10 Субботний турнир")

    url = f"/api/clubs/{club.id}/tournaments/{tournament['id']}"
    assert entries(client, url) == [
        ("registration_cancelled", PLAYER, "Мария Иванова", ""),
        ("registered", PLAYER, "Мария Иванова", ""),
    ]


def test_check_ins_and_drop_outs_are_logged_with_the_money_taken_and_given_back(
    client: TestClient, club: Club
) -> None:
    url, (guest,) = ready_tournament(client, club, arrived=1)
    registration = f"{url}/registrations/{guest['id']}"

    client.delete(f"{registration}/check-in")
    client.post(f"{registration}/check-in", json={"payment_method": "card"})
    client.delete(registration)

    assert entries(client, url) == [
        ("registration_cancelled", ADMIN, "Гость 01", "Возвращено 2 000 ₽"),
        ("checked_in", ADMIN, "Гость 01", "2 000 ₽ картой"),
        ("check_in_undone", ADMIN, "Гость 01", "Возвращено 2 000 ₽"),
        ("checked_in", ADMIN, "Гость 01", "2 000 ₽ наличными"),
        ("registered", ADMIN, "Гость 01", ""),
    ]


def test_the_blind_clock_is_logged_with_the_level_and_the_time_left(
    client: TestClient, club: Club, clock: FakeClock
) -> None:
    # Level 1 and level 2 of 20 minutes, a break, level 3.
    url, _ = ready_tournament(client, club, arrived=3)

    client.post(f"{url}/start")
    clock.advance(timedelta(minutes=5))
    client.post(f"{url}/pause")
    clock.advance(timedelta(minutes=3))
    client.post(f"{url}/resume")
    client.post(f"{url}/next-level")
    client.post(f"{url}/next-level")
    client.post(f"{url}/previous-level")

    assert entries(client, url)[:6] == [
        ("level_changed", ADMIN, None, "Перерыв → уровень 2"),
        ("level_changed", ADMIN, None, "Уровень 2 → перерыв"),
        ("level_changed", ADMIN, None, "Уровень 1 → уровень 2"),
        ("resumed", ADMIN, None, "Уровень 1, осталось 15:00"),
        ("paused", ADMIN, None, "Уровень 1, осталось 15:00"),
        ("started", ADMIN, None, "Игроков: 3, столов: 1"),
    ]


def seat_of(game: dict[str, Any], player: dict[str, Any]) -> str:
    seated = next(s for s in game["in_game"] if s["player"]["id"] == player["id"])
    return f"Стол {seated['table']}, место {seated['seat']}"


def test_knock_outs_re_entries_add_ons_and_late_seats_are_logged_with_seat_and_money(
    client: TestClient, club: Club
) -> None:
    url, (first, second, _, late) = ready_tournament(client, club, arrived=3, not_arrived=1)
    client.post(f"{url}/start")

    client.post(f"{url}/players/{first['id']}/knock-out")
    back = client.post(f"{url}/players/{first['id']}/undo-knock-out").json()
    client.post(f"{url}/players/{first['id']}/knock-out")
    reentered = client.post(f"{url}/players/{first['id']}/reentry", json=CASH).json()
    client.post(f"{url}/next-level")
    client.post(f"{url}/players/{second['id']}/addon", json=CASH)
    seated = client.post(f"{url}/players/{late['id']}/seat", json=CASH).json()

    assert entries(client, url)[:7] == [
        ("seated_late", ADMIN, "Гость 04", f"{seat_of(seated, late)}; 2 000 ₽ наличными"),
        ("addon", ADMIN, "Гость 02", "1 000 ₽ наличными"),
        ("level_changed", ADMIN, None, "Уровень 1 → уровень 2"),
        ("reentry", ADMIN, "Гость 01", f"{seat_of(reentered, first)}; 2 000 ₽ наличными"),
        ("knocked_out", ADMIN, "Гость 01", "Место 3"),
        ("knock_out_undone", ADMIN, "Гость 01", seat_of(back, first)),
        ("knocked_out", ADMIN, "Гость 01", "Место 3"),
    ]


def test_moves_and_the_final_table_draw_are_logged_from_seat_to_seat(
    client: TestClient, club: Club
) -> None:
    # Tables of three and two.
    url, _ = ready_tournament(client, club, arrived=5, seats_per_table=3)
    game = client.post(f"{url}/start").json()
    at_table = {t: [s for s in game["in_game"] if s["table"] == t] for t in (1, 2)}
    small, big = sorted(at_table.values(), key=len)
    # Three players against one: the suggestion evens them up.
    client.post(f"{url}/players/{small[0]['player']['id']}/knock-out")
    move = client.get(f"{url}/game").json()["suggested_move"]
    client.post(
        f"{url}/players/{move['player']['id']}/move",
        json={"table": move["to_table"], "seat": move["to_seat"]},
    )
    stays = next(s for s in big if s["player"]["id"] != move["player"]["id"])
    free_seat = ({1, 2, 3} - {s["seat"] for s in big if s["player"]["id"] != move["player"]["id"]}).pop()
    client.post(
        f"{url}/players/{stays['player']['id']}/move",
        json={"table": stays["table"], "seat": free_seat},
    )
    before = client.get(f"{url}/game").json()["in_game"]

    # Three left fit at one table.
    client.post(f"{url}/players/{small[1]['player']['id']}/knock-out")

    after = client.get(f"{url}/game").json()["in_game"]
    log = entries(client, url)
    left = [s for s in before if s["player"]["id"] != small[1]["player"]["id"]]
    assert sorted(e for e in log if e[0] == "final_table") == sorted(
        (
            "final_table",
            ADMIN,
            s["player"]["name"],
            f"Стол {s['table']}, место {s['seat']} → стол 1, место "
            f"{next(a['seat'] for a in after if a['player']['id'] == s['player']['id'])}",
        )
        for s in left
    )
    assert [e for e in log if e[0] == "moved"] == [
        (
            "moved",
            ADMIN,
            stays["player"]["name"],
            f"Стол {stays['table']}, место {stays['seat']} → стол {stays['table']}, "
            f"место {free_seat}, вручную",
        ),
        (
            "moved",
            ADMIN,
            move["player"]["name"],
            f"Стол {move['from_table']}, место {move['from_seat']} → стол {move['to_table']}, "
            f"место {move['to_seat']}, по подсказке",
        ),
    ]


def test_a_corrected_place_is_logged_from_place_to_place(client: TestClient, club: Club) -> None:
    # The last one added wins.
    url, (third, _, _) = played_tournament(client, club, players=3)

    client.put(f"{url}/results/{third['id']}", json={"place": 1})

    assert entries(client, url)[0] == ("place_corrected", ADMIN, "Гость 01", "Место 3 → 1")


def test_a_storno_and_a_changed_payment_method_are_logged_with_the_operation(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=2)
    first, second = client.get(f"{url}/cashier").json()["transactions"]

    client.post(f"{url}/cashier/transactions/{first['id']}/reverse")
    client.post(
        f"{url}/cashier/transactions/{second['id']}/payment-method", json={"payment_method": "card"}
    )

    assert entries(client, url)[:2] == [
        (
            "payment_method_changed",
            ADMIN,
            "Гость 02",
            f"Операция № {second['id']}, бай-ин 2 000 ₽: наличными → картой",
        ),
        ("storno", ADMIN, "Гость 01", f"Операция № {first['id']}, бай-ин 2 000 ₽ наличными"),
    ]


def test_an_edited_tournament_is_logged_with_what_changed_and_a_cancelled_one_with_the_refund(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=2)
    unchanged = a_tournament(starts_at=TONIGHT)

    client.put(url, json=unchanged)
    client.put(
        url,
        json=unchanged
        | {
            "starts_at": "2026-09-26T20:00:00Z",
            "buy_in": 2500,
            "structure": [a_level(100, 200, minutes=15), a_level(200, 400), a_break(), a_level(300, 600)],
        },
    )
    client.post(f"{url}/cancel")

    assert entries(client, url)[:2] == [
        ("tournament_cancelled", ADMIN, None, "Возвращено 4 000 ₽"),
        (
            "tournament_edited",
            ADMIN,
            None,
            "Начало: 27.09.2026 02:00 → 27.09.2026 03:00; Бай-ин: 2 000 ₽ → 2 500 ₽; "
            "Структура блайндов",
        ),
    ]
    assert [e[0] for e in entries(client, url)].count("tournament_edited") == 1


def test_the_log_is_filtered_by_player_to_trace_one_players_evening(
    client: TestClient, club: Club
) -> None:
    url, (first, second) = ready_tournament(client, club, arrived=2)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{first['id']}/knock-out")

    assert entries(client, url, player_id=second["id"]) == [
        ("checked_in", ADMIN, "Гость 02", "2 000 ₽ наличными"),
        ("registered", ADMIN, "Гость 02", ""),
    ]


def test_an_admin_sees_only_their_own_clubs_log(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    url, _ = ready_tournament(client, club, arrived=1)
    tournament_id = url.rsplit("/", 1)[1]
    other_club = switch_to_another_club(client, caplog)

    through_our_club = client.get(f"{url}/log")
    through_their_club = client.get(f"/api/clubs/{other_club.id}/tournaments/{tournament_id}/log")

    assert through_our_club.status_code == 403
    assert through_their_club.status_code == 404


def test_a_log_entry_can_be_neither_changed_nor_deleted(client: TestClient, club: Club) -> None:
    url, _ = ready_tournament(client, club, arrived=1)
    entry_id = client.get(f"{url}/log").json()[0]["id"]

    changed = client.put(f"{url}/log/{entry_id}", json={"details": "Ничего не было"})
    deleted = client.delete(f"{url}/log/{entry_id}")
    cleared = client.delete(f"{url}/log")

    assert (changed.status_code, deleted.status_code, cleared.status_code) == (404, 404, 405)
    assert len(entries(client, url)) == 2


def test_a_refused_action_leaves_nothing_in_the_log(client: TestClient, club: Club) -> None:
    url, (guest,) = ready_tournament(client, club, arrived=0, not_arrived=1)
    before = entries(client, url)

    # One player is not enough to start, and a check-in without a payment method is refused.
    refused = client.post(f"{url}/start")
    unpaid = client.post(f"{url}/registrations/{guest['id']}/check-in")

    assert (refused.status_code, unpaid.status_code) == (409, 422)
    assert entries(client, url) == before


def test_a_place_corrected_to_where_it_was_is_not_logged(client: TestClient, club: Club) -> None:
    url, (third, _, _) = played_tournament(client, club, players=3)

    client.put(f"{url}/results/{third['id']}", json={"place": 3})

    assert entries(client, url)[0][0] != "place_corrected"
