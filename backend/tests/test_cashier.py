import csv
from io import StringIO
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.factories import create_admin, create_club
from tests.game import CASH, TONIGHT, ready_tournament
from tests.login import log_in
from tests.players import a_player, switch_to_another_club
from tests.tournaments import a_tournament


def operations(cashier: dict[str, Any]) -> list[tuple[str, str, int, str, str]]:
    return [
        (t["kind"], t["player"]["name"], t["amount"], t["payment_method"], t["admin"]["name"])
        for t in cashier["transactions"]
    ]


def csv_rows(exported: bytes) -> list[list[str]]:
    return list(csv.reader(StringIO(exported.decode("utf-8-sig")), delimiter=";"))


def test_a_check_in_takes_the_buy_in_in_cash_or_by_card(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=0, not_arrived=2, buy_in=2500)

    by_cash = client.post(
        f"{url}/registrations/{players[0]['id']}/check-in", json={"payment_method": "cash"}
    )
    by_card = client.post(
        f"{url}/registrations/{players[1]['id']}/check-in", json={"payment_method": "card"}
    )

    assert (by_cash.status_code, by_card.status_code) == (200, 200)
    assert operations(client.get(f"{url}/cashier").json()) == [
        ("buy_in", "Гость 01", 2500, "cash", "Администратор"),
        ("buy_in", "Гость 02", 2500, "card", "Администратор"),
    ]


def test_a_check_in_needs_a_payment_method_and_takes_the_buy_in_once(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=0, not_arrived=1)
    check_in = f"{url}/registrations/{players[0]['id']}/check-in"

    unpaid = client.post(check_in)
    client.post(check_in, json={"payment_method": "cash"})
    again = client.post(check_in, json={"payment_method": "card"})

    assert unpaid.status_code == 422
    assert unpaid.json()["detail"] == ["Укажите способ оплаты: наличные или карта"]
    assert again.status_code == 200
    assert operations(client.get(f"{url}/cashier").json()) == [
        ("buy_in", "Гость 01", 2000, "cash", "Администратор")
    ]


def test_a_free_tournament_takes_no_money(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=0, not_arrived=1, buy_in=0)

    checked_in = client.post(f"{url}/registrations/{players[0]['id']}/check-in")

    assert checked_in.json()["status"] == "checked_in"
    assert client.get(f"{url}/cashier").json()["transactions"] == []


def test_an_undone_check_in_gives_the_buy_in_back_by_a_storno(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=1)

    client.delete(f"{url}/registrations/{players[0]['id']}/check-in")

    cashier = client.get(f"{url}/cashier").json()
    buy_in, storno = cashier["transactions"]
    assert (buy_in["amount"], buy_in["reversed_by_id"], buy_in["reverses_id"]) == (2000, storno["id"], None)
    assert (storno["amount"], storno["reversed_by_id"], storno["reverses_id"]) == (-2000, None, buy_in["id"])
    assert (storno["kind"], storno["payment_method"]) == ("buy_in", "cash")
    assert cashier["total"] == 0
    assert cashier["by_kind"][0] == {"kind": "buy_in", "count": 0, "amount": 0}


def test_the_admin_is_told_what_was_actually_given_back(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2, not_arrived=1)
    # The buy-in goes up after two players have paid the old one.
    client.put(url, json=a_tournament(starts_at=TONIGHT, buy_in=2500))

    undone = client.delete(f"{url}/registrations/{players[0]['id']}/check-in")
    dropped = client.delete(f"{url}/registrations/{players[1]['id']}")
    unpaid = client.delete(f"{url}/registrations/{players[2]['id']}")

    assert undone.json() == {"player": players[0], "status": "registered", "refunded": 2000}
    assert dropped.status_code == 200
    assert dropped.json() == {"refunded": 2000}
    assert unpaid.json() == {"refunded": 0}


def test_a_paid_player_who_drops_out_gets_the_buy_in_back(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2)

    client.delete(f"{url}/registrations/{players[0]['id']}")

    cashier = client.get(f"{url}/cashier").json()
    assert [(t["player"]["name"], t["amount"]) for t in cashier["transactions"]] == [
        ("Гость 01", 2000),
        ("Гость 02", 2000),
        ("Гость 01", -2000),
    ]
    assert cashier["total"] == 2000


def test_a_cancelled_tournament_gives_every_buy_in_back(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2, not_arrived=1)

    client.post(f"{url}/cancel")

    cashier = client.get(f"{url}/cashier").json()
    assert [t["amount"] for t in cashier["transactions"]] == [2000, 2000, -2000, -2000]
    assert cashier["total"] == 0


def test_a_re_entry_is_paid_like_a_buy_in(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=3, buy_in=1500)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")
    reentry = f"{url}/players/{players[0]['id']}/reentry"

    unpaid = client.post(reentry)
    paid = client.post(reentry, json={"payment_method": "card"})

    assert unpaid.status_code == 422
    assert unpaid.json()["detail"] == ["Укажите способ оплаты: наличные или карта"]
    assert paid.status_code == 200
    assert operations(client.get(f"{url}/cashier").json())[3:] == [
        ("reentry", "Гость 01", 1500, "card", "Администратор")
    ]


def test_an_add_on_is_paid_at_its_own_price(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2, addon_at_level=1, addon_price=1000)
    client.post(f"{url}/start")
    addon = f"{url}/players/{players[0]['id']}/addon"

    unpaid = client.post(addon)
    paid = client.post(addon, json={"payment_method": "cash"})

    assert unpaid.status_code == 422
    assert paid.status_code == 200
    assert operations(client.get(f"{url}/cashier").json())[2:] == [
        ("addon", "Гость 01", 1000, "cash", "Администратор")
    ]


def test_a_late_player_pays_the_buy_in_on_sitting_down(client: TestClient, club: Club) -> None:
    url, players = ready_tournament(client, club, arrived=2, not_arrived=1)
    client.post(f"{url}/start")
    seat = f"{url}/players/{players[2]['id']}/seat"

    unpaid = client.post(seat)
    seated = client.post(seat, json={"payment_method": "card"})

    assert unpaid.status_code == 422
    assert seated.status_code == 200
    assert operations(client.get(f"{url}/cashier").json())[2:] == [
        ("buy_in", "Гость 03", 2000, "card", "Администратор")
    ]


def test_a_transaction_names_the_admin_who_took_the_money(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    url, players = ready_tournament(client, club, arrived=0, not_arrived=2)
    client.post(f"{url}/registrations/{players[0]['id']}/check-in", json=CASH)
    create_admin(club, phone="+79130000009", name="Ольга Кассирова")
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000009")

    client.post(f"{url}/registrations/{players[1]['id']}/check-in", json=CASH)

    assert [admin for *_, admin in operations(client.get(f"{url}/cashier").json())] == [
        "Администратор",
        "Ольга Кассирова",
    ]


CARD = {"payment_method": "card"}


def test_the_summary_adds_up_by_operation_and_by_payment_method(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(
        client, club, arrived=0, not_arrived=4, buy_in=2000, addon_at_level=1, addon_price=1000
    )
    for player, payment in zip(players, [CASH, CASH, CARD, CARD]):
        client.post(f"{url}/registrations/{player['id']}/check-in", json=payment)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")
    client.post(f"{url}/players/{players[0]['id']}/reentry", json=CARD)
    client.post(f"{url}/players/{players[1]['id']}/addon", json=CASH)
    client.post(f"{url}/players/{players[2]['id']}/addon", json=CARD)
    client.post(f"{url}/players/{players[3]['id']}/addon", json=CASH)

    cashier = client.get(f"{url}/cashier").json()

    assert cashier["by_kind"] == [
        {"kind": "buy_in", "count": 4, "amount": 8000},
        {"kind": "reentry", "count": 1, "amount": 2000},
        {"kind": "addon", "count": 3, "amount": 3000},
    ]
    assert cashier["by_method"] == [
        {"payment_method": "cash", "amount": 6000},
        {"payment_method": "card", "amount": 7000},
    ]
    assert cashier["total"] == 13000


def test_a_tournament_with_no_payments_has_an_empty_cashier(client: TestClient, club: Club) -> None:
    url, _ = ready_tournament(client, club, arrived=0)

    assert client.get(f"{url}/cashier").json() == {
        "by_kind": [
            {"kind": "buy_in", "count": 0, "amount": 0},
            {"kind": "reentry", "count": 0, "amount": 0},
            {"kind": "addon", "count": 0, "amount": 0},
        ],
        "by_method": [
            {"payment_method": "cash", "amount": 0},
            {"payment_method": "card", "amount": 0},
        ],
        "total": 0,
        "transactions": [],
    }


def test_a_mistaken_transaction_is_reversed_and_stays_in_the_history(
    client: TestClient, club: Club
) -> None:
    url, players = ready_tournament(client, club, arrived=3, addon_at_level=1, addon_price=1000)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/addon", json=CARD)
    addon = client.get(f"{url}/cashier").json()["transactions"][-1]

    reversed_ = client.post(f"{url}/cashier/transactions/{addon['id']}/reverse")

    assert reversed_.status_code == 200
    cashier = reversed_.json()
    assert cashier == client.get(f"{url}/cashier").json()
    addon_now, storno = cashier["transactions"][3:]
    assert (addon_now["amount"], addon_now["reversed_by_id"]) == (1000, storno["id"])
    assert (storno["kind"], storno["amount"], storno["payment_method"]) == ("addon", -1000, "card")
    assert cashier["transactions"][-1]["reverses_id"] == addon["id"]
    assert cashier["by_kind"][2] == {"kind": "addon", "count": 0, "amount": 0}
    assert cashier["total"] == 6000


def test_a_transaction_is_reversed_once_and_a_storno_is_not_reversed(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=1)
    buy_in = client.get(f"{url}/cashier").json()["transactions"][0]
    client.post(f"{url}/cashier/transactions/{buy_in['id']}/reverse")
    storno = client.get(f"{url}/cashier").json()["transactions"][1]

    again = client.post(f"{url}/cashier/transactions/{buy_in['id']}/reverse")
    of_storno = client.post(f"{url}/cashier/transactions/{storno['id']}/reverse")
    missing = client.post(f"{url}/cashier/transactions/999/reverse")

    assert (again.status_code, again.json()["detail"]) == (409, "Операция уже сторнирована")
    assert (of_storno.status_code, of_storno.json()["detail"]) == (409, "Сторно не сторнируют")
    assert (missing.status_code, missing.json()["detail"]) == (404, "Операция не найдена")
    assert len(client.get(f"{url}/cashier").json()["transactions"]) == 2


def test_a_wrong_payment_method_is_reversed_and_paid_again_the_other_way(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=1)
    buy_in = client.get(f"{url}/cashier").json()["transactions"][0]
    change = f"{url}/cashier/transactions/{buy_in['id']}/payment-method"

    changed = client.post(change, json=CARD)

    assert changed.status_code == 200
    cashier = changed.json()
    assert [(t["amount"], t["payment_method"]) for t in cashier["transactions"]] == [
        (2000, "cash"),
        (-2000, "cash"),
        (2000, "card"),
    ]
    assert [t["reversed_by_id"] is not None for t in cashier["transactions"]] == [True, False, False]
    assert cashier["transactions"][2]["replaces_id"] == buy_in["id"]
    assert cashier["by_kind"][0] == {"kind": "buy_in", "count": 1, "amount": 2000}
    assert cashier["by_method"] == [
        {"payment_method": "cash", "amount": 0},
        {"payment_method": "card", "amount": 2000},
    ]
    rows = csv_rows(client.get(f"{url}/cashier.csv").content)
    assert rows[5][-1] == f"Взамен операции № {buy_in['id']}"
    already_reversed = client.post(change, json=CASH)
    assert (already_reversed.status_code, already_reversed.json()["detail"]) == (
        409,
        "Операция уже сторнирована",
    )


def test_a_payment_method_is_changed_to_the_other_one(client: TestClient, club: Club) -> None:
    url, _ = ready_tournament(client, club, arrived=1)
    buy_in = client.get(f"{url}/cashier").json()["transactions"][0]

    same = client.post(f"{url}/cashier/transactions/{buy_in['id']}/payment-method", json=CASH)

    assert (same.status_code, same.json()["detail"]) == (409, "Операция и так оплачена наличными")
    assert len(client.get(f"{url}/cashier").json()["transactions"]) == 1


def test_the_cashier_is_exported_to_csv_for_excel(client: TestClient, club: Club) -> None:
    # Starts at 19:00 UTC, 02:00 the next day in the league's time (UTC+7).
    url, players = ready_tournament(client, club, arrived=0, not_arrived=2, name="Ночной турнир")
    client.post(f"{url}/registrations/{players[0]['id']}/check-in", json=CASH)
    client.post(f"{url}/registrations/{players[1]['id']}/check-in", json=CARD)
    client.delete(f"{url}/registrations/{players[1]['id']}/check-in")

    exported = client.get(f"{url}/cashier.csv")

    assert exported.status_code == 200
    assert exported.headers["content-type"] == "text/csv; charset=utf-8"
    assert exported.headers["content-disposition"] == f'attachment; filename="kassa-{url.split('/')[-1]}.csv"'
    # With a byte order mark and semicolons, Excel opens it in Russian as it is.
    assert exported.content.startswith("﻿".encode())
    rows = csv_rows(exported.content)
    assert rows == [
        ["Касса турнира «Ночной турнир», начало 27.09.2026 02:00"],
        [],
        ["№", "Время", "Операция", "Игрок", "Способ оплаты", "Сумма", "Администратор", "Примечание"],
        ["1", "26.09.2026 19:00", "Бай-ин", "Гость 01", "Наличные", "2000", "Администратор", ""],
        ["2", "26.09.2026 19:00", "Бай-ин", "Гость 02", "Карта", "2000", "Администратор", "Сторнирована операцией № 3"],
        ["3", "26.09.2026 19:00", "Бай-ин", "Гость 02", "Карта", "-2000", "Администратор", "Сторно операции № 2"],
        [],
        ["Итог", "Операций", "Сумма"],
        ["Бай-ин", "1", "2000"],
        ["Re-entry", "0", "0"],
        ["Add-on", "0", "0"],
        ["Наличные", "", "2000"],
        ["Карта", "", "0"],
        ["Всего", "", "2000"],
    ]


def test_a_name_in_the_csv_is_never_taken_for_an_excel_formula(
    client: TestClient, club: Club
) -> None:
    url, _ = ready_tournament(client, club, arrived=0, name="=Ночной турнир")
    player = client.post(
        f"/api/clubs/{club.id}/players", json=a_player(name="=HYPERLINK(\"x\")", phone="+79135550000")
    ).json()["player"]
    client.post(f"{url}/registrations", json={"player_id": player["id"]})
    client.post(f"{url}/registrations/{player['id']}/check-in", json=CASH)

    rows = csv_rows(client.get(f"{url}/cashier.csv").content)

    assert rows[0][0].startswith("Касса турнира «=Ночной турнир»")
    assert rows[3][3] == "'=HYPERLINK(\"x\")"
    # Amounts stay numbers, storno ones negative.
    assert rows[3][5] == "2000"


def test_admin_sees_and_corrects_only_their_own_clubs_cashier(
    client: TestClient, club: Club, caplog: pytest.LogCaptureFixture
) -> None:
    url, _ = ready_tournament(client, club, arrived=1)
    buy_in = client.get(f"{url}/cashier").json()["transactions"][0]
    other_club = switch_to_another_club(client, caplog)
    own_url, _ = ready_tournament(client, other_club, arrived=1)
    via_own_club = url.replace(f"/clubs/{club.id}/", f"/clubs/{other_club.id}/")
    transaction = f"cashier/transactions/{buy_in['id']}"

    for base, refused in [(url, 403), (via_own_club, 404)]:
        assert client.get(f"{base}/cashier").status_code == refused
        assert client.get(f"{base}/cashier.csv").status_code == refused
        assert client.post(f"{base}/{transaction}/reverse").status_code == refused
        assert client.post(f"{base}/{transaction}/payment-method", json=CARD).status_code == refused
    # Nor through their own tournament with the other club's transaction.
    assert client.post(f"{own_url}/{transaction}/reverse").status_code == 404
    assert len(client.get(f"{own_url}/cashier").json()["transactions"]) == 1

    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000001")
    assert len(client.get(f"{url}/cashier").json()["transactions"]) == 1


def test_the_cashier_requires_login(client: TestClient) -> None:
    club = create_club()
    url = f"/api/clubs/{club.id}/tournaments/1"

    assert client.get(f"{url}/cashier").status_code == 401
    assert client.get(f"{url}/cashier.csv").status_code == 401
    assert client.post(f"{url}/cashier/transactions/1/reverse").status_code == 401
    assert client.post(f"{url}/cashier/transactions/1/payment-method", json=CARD).status_code == 401
