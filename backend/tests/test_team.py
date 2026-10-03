"""The club's team: the owner sees the club's admins, adds one by name and phone and removes one.
Owners are the league's to change. A removed admin loses access at once, but stays the author
of what they did."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.models import Club
from tests.clock import FakeClock
from tests.factories import create_admin, create_club
from tests.game import ready_tournament
from tests.login import log_in

OWNER_PHONE = "+79130000009"


@pytest.fixture
def owned_club(client: TestClient, caplog: pytest.LogCaptureFixture, clock: FakeClock) -> Club:
    """A club whose owner is logged in, with one admin, and the clock fixed at 2026-09-26 12:00
    UTC."""
    club = create_club(name="Покер-клуб «Обь»")
    create_admin(club, phone=OWNER_PHONE, name="Олег Владимиров", role="owner")
    create_admin(club, phone="+79130000001", name="Анна Соколова")
    log_in(client, caplog, OWNER_PHONE)
    return club


@pytest.fixture
def admins_browser() -> Iterator[TestClient]:
    """Another browser, with a cookie jar of its own, for an admin logged in at the same time."""
    from app.main import app

    with TestClient(app) as browser:
        yield browser


def member_id(client: TestClient, club: Club, phone: str) -> int:
    members = client.get(f"/api/clubs/{club.id}/team").json()
    return int(next(member["id"] for member in members if member["phone"] == phone))


def codes_sent(caplog: pytest.LogCaptureFixture, phone: str) -> int:
    """How many login codes the backend has sent to the phone (written to its log)."""
    return sum(1 for record in caplog.records if phone in record.getMessage())


def team(client: TestClient, club: Club) -> list[tuple[str, str, str]]:
    """The team as the owner sees it: name, phone, role."""
    response = client.get(f"/api/clubs/{club.id}/team")
    assert response.status_code == 200, response.json()
    return [(member["name"], member["phone"], member["role"]) for member in response.json()]


def test_the_owner_sees_the_clubs_owners_and_admins_and_no_one_elses(
    client: TestClient, owned_club: Club
) -> None:
    create_admin(owned_club, phone="+79130000002", name="Борис Аксёнов")
    other_club = create_club(name="Покер-клуб «Енисей»")
    create_admin(other_club, phone="+79130000019", name="Дмитрий Орлов")

    assert team(client, owned_club) == [
        ("Олег Владимиров", OWNER_PHONE, "owner"),
        ("Анна Соколова", "+79130000001", "admin"),
        ("Борис Аксёнов", "+79130000002", "admin"),
    ]


def test_an_admin_the_owner_adds_logs_in_to_the_club(
    client: TestClient, caplog: pytest.LogCaptureFixture, owned_club: Club
) -> None:
    added = client.post(
        f"/api/clubs/{owned_club.id}/team", json={"name": "Виктор Осипов", "phone": "8 913 000-00-05"}
    )
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000005")

    assert added.status_code == 201
    assert added.json()["outcome"] == "added"
    me = client.get("/api/auth/me").json()
    assert (me["admin"]["name"], me["admin"]["role"]) == ("Виктор Осипов", "admin")
    assert me["club"]["id"] == owned_club.id


def test_a_removed_admin_is_logged_out_at_once_and_gets_no_login_code(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    owned_club: Club,
    admins_browser: TestClient,
) -> None:
    log_in(admins_browser, caplog, "+79130000001")
    assert admins_browser.get("/api/auth/me").status_code == 200

    removed = client.delete(f"/api/clubs/{owned_club.id}/team/{member_id(client, owned_club, '+79130000001')}")

    assert removed.status_code == 204
    assert admins_browser.get("/api/auth/me").status_code == 401
    codes_before = codes_sent(caplog, "+79130000001")
    admins_browser.post("/api/auth/request-code", json={"phone": "+79130000001"})
    assert codes_sent(caplog, "+79130000001") == codes_before
    assert team(client, owned_club) == [("Олег Владимиров", OWNER_PHONE, "owner")]


def test_a_removed_admin_stays_the_author_of_what_they_did_in_the_cashier_and_the_log(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    owned_club: Club,
    admins_browser: TestClient,
) -> None:
    log_in(admins_browser, caplog, "+79130000001")
    url, _ = ready_tournament(admins_browser, owned_club, arrived=1)

    client.delete(f"/api/clubs/{owned_club.id}/team/{member_id(client, owned_club, '+79130000001')}")

    cashier = client.get(f"{url}/cashier").json()
    log = client.get(f"{url}/log").json()
    assert [t["admin"]["name"] for t in cashier["transactions"]] == ["Анна Соколова"]
    assert {entry["admin"]["name"] for entry in log} == {"Анна Соколова"}


def test_adding_a_removed_admins_phone_again_brings_them_back(
    client: TestClient, caplog: pytest.LogCaptureFixture, owned_club: Club
) -> None:
    anna = member_id(client, owned_club, "+79130000001")
    client.delete(f"/api/clubs/{owned_club.id}/team/{anna}")

    returned = client.post(
        f"/api/clubs/{owned_club.id}/team", json={"name": "Анна С.", "phone": "+7 913 000-00-01"}
    )

    assert returned.status_code == 200
    assert returned.json()["outcome"] == "returned"
    # The same person as before, under the name the club has known them by.
    assert returned.json()["admin"]["id"] == anna
    assert ("Анна Соколова", "+79130000001", "admin") in team(client, owned_club)
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000001")
    assert client.get("/api/auth/me").json()["admin"]["id"] == anna


OTHER_CLUBS_STAFF = (
    "Этот телефон уже у сотрудника другого клуба лиги. Один человек может быть в команде только "
    "одного клуба"
)


@pytest.mark.parametrize("removed_there", [False, True], ids=["working there", "removed there"])
def test_another_clubs_staff_member_cannot_be_added(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    owned_club: Club,
    admins_browser: TestClient,
    removed_there: bool,
) -> None:
    other_club = create_club(name="Покер-клуб «Енисей»")
    create_admin(other_club, phone="+79130000019", name="Дмитрий Орлов")
    create_admin(other_club, phone="+79130000029", name="Ирина Белова", role="owner")
    if removed_there:
        log_in(admins_browser, caplog, "+79130000029")
        orlov = member_id(admins_browser, other_club, "+79130000019")
        admins_browser.delete(f"/api/clubs/{other_club.id}/team/{orlov}")

    refused = client.post(
        f"/api/clubs/{owned_club.id}/team", json={"name": "Дмитрий Орлов", "phone": "+79130000019"}
    )

    assert refused.status_code == 409
    assert refused.json()["detail"] == OTHER_CLUBS_STAFF
    assert "+79130000019" not in [phone for _, phone, _ in team(client, owned_club)]


@pytest.mark.parametrize("phone", ["+79130000001", OWNER_PHONE], ids=["an admin", "the owner"])
def test_someone_already_in_the_team_is_not_added_again(
    client: TestClient, owned_club: Club, phone: str
) -> None:
    before = team(client, owned_club)

    refused = client.post(f"/api/clubs/{owned_club.id}/team", json={"name": "Кто-то", "phone": phone})

    assert refused.status_code == 409
    assert refused.json()["detail"].endswith("уже в команде клуба")
    assert team(client, owned_club) == before


@pytest.mark.parametrize("phone", [OWNER_PHONE, "+79130000008"], ids=["themselves", "another owner"])
def test_the_owner_cannot_remove_an_owner(client: TestClient, owned_club: Club, phone: str) -> None:
    create_admin(owned_club, phone="+79130000008", name="Яна Владимирова", role="owner")
    before = team(client, owned_club)

    refused = client.delete(f"/api/clubs/{owned_club.id}/team/{member_id(client, owned_club, phone)}")

    assert refused.status_code == 409
    assert refused.json()["detail"] == "Владельцев клуба меняет лига"
    assert team(client, owned_club) == before


def test_only_the_clubs_own_owner_sees_and_changes_its_team_and_reads_its_log(
    client: TestClient, caplog: pytest.LogCaptureFixture, owned_club: Club
) -> None:
    anna = member_id(client, owned_club, "+79130000001")
    other_club = create_club(name="Покер-клуб «Енисей»")
    create_admin(other_club, phone="+79130000029", role="owner")
    url = f"/api/clubs/{owned_club.id}/team"
    newcomer = {"name": "Виктор Осипов", "phone": "+79130000005"}

    def attempts() -> list[int]:
        return [
            client.get(url).status_code,
            client.post(url, json=newcomer).status_code,
            client.delete(f"{url}/{anna}").status_code,
            client.get(f"/api/clubs/{owned_club.id}/log").status_code,
        ]

    client.post("/api/auth/logout")
    anonymous = attempts()
    log_in(client, caplog, "+79130000001")
    admin = attempts()
    admins_refusal = client.get(url).json()["detail"]
    client.post("/api/auth/logout")
    log_in(client, caplog, "+79130000029")
    other_owner = attempts()

    assert anonymous == [401, 401, 401, 401]
    assert admin == [403, 403, 403, 403]
    assert admins_refusal == "Это видит только владелец клуба"
    assert other_owner == [403, 403, 403, 403]
    client.post("/api/auth/logout")
    log_in(client, caplog, OWNER_PHONE)
    assert [phone for _, phone, _ in team(client, owned_club)] == [OWNER_PHONE, "+79130000001"]


def test_a_new_admin_needs_a_name_and_a_russian_phone(client: TestClient, owned_club: Club) -> None:
    before = team(client, owned_club)

    refused = client.post(f"/api/clubs/{owned_club.id}/team", json={"name": " ", "phone": "12345"})

    assert refused.status_code == 422
    assert refused.json()["detail"] == [
        "Укажите имя сотрудника",
        "Телефон: нужен российский номер из 11 цифр, например +7 913 555-12-34",
    ]
    assert team(client, owned_club) == before


def club_log(client: TestClient, club: Club) -> list[tuple[str, str, str]]:
    """The club's own log as the owner reads it: action, who did it, details."""
    response = client.get(f"/api/clubs/{club.id}/log")
    assert response.status_code == 200, response.json()
    return [
        (entry["action"], entry["admin"]["name"], entry["details"]) for entry in response.json()
    ]


def test_the_team_changes_are_in_the_clubs_log_the_latest_first(
    client: TestClient, owned_club: Club, clock: FakeClock
) -> None:
    team_url = f"/api/clubs/{owned_club.id}/team"
    anna = member_id(client, owned_club, "+79130000001")
    client.post(team_url, json={"name": "Виктор Осипов", "phone": "+79130000005"})
    client.delete(f"{team_url}/{anna}")
    client.post(team_url, json={"name": "Анна Соколова", "phone": "+79130000001"})
    # What is done to a tournament is in the tournament's log, not the club's.
    ready_tournament(client, owned_club, arrived=1)

    assert club_log(client, owned_club) == [
        ("admin_returned", "Олег Владимиров", "Анна Соколова, +7 913 000-00-01"),
        ("admin_removed", "Олег Владимиров", "Анна Соколова, +7 913 000-00-01"),
        ("admin_added", "Олег Владимиров", "Виктор Осипов, +7 913 000-00-05"),
    ]
    assert client.get(f"/api/clubs/{owned_club.id}/log").json()[0]["created_at"] == "2026-09-26T12:00:00Z"
