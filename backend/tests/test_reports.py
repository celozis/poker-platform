import csv
from datetime import UTC, datetime
from io import StringIO
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.clock import FakeClock
from tests.factories import create_admin, create_club
from tests.game import CASH, played_tournament, ready_tournament
from tests.login import log_in

CARD = {"payment_method": "card"}
# The week of FakeClock's 2026-09-26, Monday to Sunday.
THIS_WEEK = "from=2026-09-21&to=2026-09-27"


@pytest.fixture
def owned_club(client: TestClient, caplog: pytest.LogCaptureFixture, clock: FakeClock) -> Club:
    """A club whose owner is logged in, with the clock fixed at 2026-09-26 12:00 UTC. The owner
    runs the club's tournaments too, as an admin would."""
    club = create_club(name="Покер-клуб «Обь»")
    create_admin(club, phone="+79130000009", name="Олег Владимиров", role="owner")
    log_in(client, caplog, "+79130000009")
    return club


def test_the_finances_add_up_the_money_of_the_periods_tournaments(
    client: TestClient, owned_club: Club, clock: FakeClock
) -> None:
    url, players = ready_tournament(
        client, owned_club, arrived=0, not_arrived=3, addon_at_level=1, addon_price=1000
    )
    for player, payment in zip(players, [CASH, CASH, CARD]):
        client.post(f"{url}/registrations/{player['id']}/check-in", json=payment)
    client.post(f"{url}/start")
    client.post(f"{url}/players/{players[0]['id']}/knock-out")
    client.post(f"{url}/players/{players[0]['id']}/reentry", json=CARD)
    client.post(f"{url}/players/{players[1]['id']}/addon", json=CASH)
    # A second tournament of the week, where one check-in was given back by a storno.
    url, players = ready_tournament(client, owned_club, arrived=3, buy_in=1500)
    client.delete(f"{url}/registrations/{players[2]['id']}/check-in")
    client.post(f"{url}/start")
    # Next week's tournament is not in this week's report.
    clock.now = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
    ready_tournament(client, owned_club, arrived=1, starts_at="2026-09-28T19:00:00+07:00")

    report = client.get(f"/api/clubs/{owned_club.id}/reports?{THIS_WEEK}")

    assert report.status_code == 200
    assert report.json()["finances"] == {
        "tournaments": 2,
        "by_kind": [
            {"kind": "buy_in", "count": 5, "amount": 9000},
            {"kind": "reentry", "count": 1, "amount": 2000},
            {"kind": "addon", "count": 1, "amount": 1000},
        ],
        "by_method": [
            {"payment_method": "cash", "amount": 8000},
            {"payment_method": "card", "amount": 4000},
        ],
        "total": 12000,
    }


def test_only_the_clubs_own_owner_sees_its_reports(
    client: TestClient, caplog: pytest.LogCaptureFixture, owned_club: Club
) -> None:
    create_admin(owned_club, phone="+79130000001", name="Анна")
    other_club = create_club(name="Покер-клуб «Енисей»")
    create_admin(other_club, phone="+79130000019", role="owner")
    reports = f"/api/clubs/{owned_club.id}/reports?{THIS_WEEK}"
    client.post("/api/auth/logout")

    anonymous = client.get(reports)
    log_in(client, caplog, "+79130000001")
    admin = client.get(reports)
    exported_by_admin = client.get(reports.replace("/reports?", "/reports.csv?"))
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000019")
    other_owner = client.get(reports)
    exported_by_other_owner = client.get(reports.replace("/reports?", "/reports.csv?"))

    assert (anonymous.status_code, admin.status_code, other_owner.status_code) == (401, 403, 403)
    assert (exported_by_admin.status_code, exported_by_other_owner.status_code) == (403, 403)


def test_the_attendance_counts_the_players_who_came_week_by_week(
    client: TestClient, owned_club: Club, clock: FakeClock
) -> None:
    clock.now = datetime(2026, 9, 17, 6, 0, tzinfo=UTC)
    url, _ = ready_tournament(
        client, owned_club, arrived=3, not_arrived=1, starts_at="2026-09-17T19:00:00+07:00"
    )
    client.post(f"{url}/start")
    clock.now = datetime(2026, 9, 26, 12, 0, tzinfo=UTC)
    url, players = ready_tournament(client, owned_club, arrived=4)
    client.post(f"{url}/start")
    # A re-entry is the same player again, and a cancelled tournament was not played.
    client.post(f"{url}/players/{players[0]['id']}/knock-out")
    client.post(f"{url}/players/{players[0]['id']}/reentry", json=CASH)
    url, _ = ready_tournament(client, owned_club, arrived=2)
    client.post(f"{url}/cancel")

    report = client.get(f"/api/clubs/{owned_club.id}/reports?from=2026-09-09&to=2026-09-27")

    # Weeks run Monday to Sunday; the first one here starts with the period, on a Wednesday.
    assert report.json()["attendance"] == {
        "weeks": [
            {"first_day": "2026-09-09", "last_day": "2026-09-13", "tournaments": 0, "participants": 0},
            {"first_day": "2026-09-14", "last_day": "2026-09-20", "tournaments": 1, "participants": 3},
            {"first_day": "2026-09-21", "last_day": "2026-09-27", "tournaments": 1, "participants": 4},
        ],
        "participants": 7,
        "average_players": 3.5,
    }


def top(rows: list[dict[str, Any]]) -> list[tuple[int, str, int, int]]:
    return [(r["position"], r["player"]["name"], r["points"], r["tournaments"]) for r in rows]


def test_the_best_players_of_the_period_by_points_and_by_tournaments_played(
    client: TestClient, owned_club: Club, clock: FakeClock
) -> None:
    played_tournament(client, owned_club, players=4)  # Гость 04: 10, 03: 4, 02: 2, 01: 0
    played_tournament(client, owned_club, players=2)  # Гость 02: 4, 01: 0
    clock.now = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
    played_tournament(client, owned_club, players=3, starts_at="2026-09-28T19:00:00+07:00")

    report = client.get(f"/api/clubs/{owned_club.id}/reports?{THIS_WEEK}").json()

    # Equal points, or equal tournaments, share a position.
    assert top(report["top_by_points"]) == [
        (1, "Гость 04", 10, 1),
        (2, "Гость 02", 6, 2),
        (3, "Гость 03", 4, 1),
        (4, "Гость 01", 0, 2),
    ]
    assert top(report["top_by_tournaments"]) == [
        (1, "Гость 02", 6, 2),
        (1, "Гость 01", 0, 2),
        (3, "Гость 04", 10, 1),
        (3, "Гость 03", 4, 1),
    ]


def test_the_best_players_are_the_first_ten(client: TestClient, owned_club: Club) -> None:
    # Knocked out in the order they were added: Гость 01 and Гость 02 finish last.
    played_tournament(client, owned_club, players=12)

    report = client.get(f"/api/clubs/{owned_club.id}/reports?{THIS_WEEK}").json()

    for best in (report["top_by_points"], report["top_by_tournaments"]):
        names = [name for _, name, *_ in top(best)]
        assert (len(names), "Гость 01" in names, "Гость 02" in names) == (10, False, False)


def test_a_period_runs_from_midnight_to_midnight_in_the_leagues_time(
    client: TestClient, owned_club: Club, clock: FakeClock
) -> None:
    clock.now = datetime(2026, 9, 27, 10, 0, tzinfo=UTC)
    ready_tournament(client, owned_club, arrived=1, starts_at="2026-09-27T23:30:00+07:00")
    # 17:30 UTC on Sunday, but already Monday in Novosibirsk.
    ready_tournament(
        client, owned_club, arrived=1, buy_in=1500, starts_at="2026-09-28T00:30:00+07:00"
    )

    this_week = client.get(f"/api/clubs/{owned_club.id}/reports?{THIS_WEEK}").json()
    next_week = client.get(f"/api/clubs/{owned_club.id}/reports?from=2026-09-28&to=2026-10-04")

    assert (this_week["finances"]["total"], next_week.json()["finances"]["total"]) == (2000, 1500)


@pytest.mark.parametrize(
    ("period", "problem"),
    [
        ("from=2026-09-27&to=2026-09-21", "Период: начало позже конца"),
        ("from=2025-09-01&to=2026-09-27", "Период: не больше 366 дней"),
        ("from=2026-09-21", "Период, по: не заполнено"),
        ("from=21.09.2026&to=2026-09-27", "Период, с: нужна дата"),
    ],
)
def test_a_report_needs_a_period_of_up_to_a_year(
    client: TestClient, owned_club: Club, period: str, problem: str
) -> None:
    report = client.get(f"/api/clubs/{owned_club.id}/reports?{period}")

    assert report.status_code == 422
    assert report.json()["detail"] == [problem]


def test_the_report_is_exported_for_excel(client: TestClient, owned_club: Club) -> None:
    played_tournament(client, owned_club, players=2)

    exported = client.get(f"/api/clubs/{owned_club.id}/reports.csv?{THIS_WEEK}")

    assert exported.status_code == 200
    assert exported.headers["content-type"] == "text/csv; charset=utf-8"
    assert 'filename="otchet-2026-09-21-2026-09-27.csv"' in exported.headers["content-disposition"]
    # Semicolons and a byte order mark, as a Russian Excel expects; a decimal comma too.
    assert exported.content.startswith("﻿".encode())
    assert list(csv.reader(StringIO(exported.content.decode("utf-8-sig")), delimiter=";")) == [
        ["Отчёт клуба «Покер-клуб «Обь»» за 21.09.2026 – 27.09.2026"],
        [],
        ["Финансы"],
        ["Турниров проведено", "1"],
        ["Операция", "Операций", "Сумма"],
        ["Бай-ин", "2", "4000"],
        ["Re-entry", "0", "0"],
        ["Add-on", "0", "0"],
        ["Наличные", "", "4000"],
        ["Карта", "", "0"],
        ["Всего", "", "4000"],
        [],
        ["Посещаемость"],
        ["Неделя", "Турниров", "Участников"],
        ["21.09.2026 – 27.09.2026", "1", "2"],
        ["Всего", "1", "2"],
        ["Среднее число игроков на турнир", "2,0"],
        [],
        ["Лучшие игроки по очкам"],
        ["Место", "Игрок", "Очки", "Турниров"],
        ["1", "Гость 02", "4", "1"],
        ["2", "Гость 01", "0", "1"],
        [],
        ["Лучшие игроки по числу турниров"],
        ["Место", "Игрок", "Турниров", "Очки"],
        ["1", "Гость 02", "1", "4"],
        ["1", "Гость 01", "1", "0"],
    ]
