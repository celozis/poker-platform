"""The league command: what the developer does at the league's request — the clubs and who owns
each — run inside the backend's container. Its result is checked through the API, as the people
it was done for see it."""

import pytest
from fastapi.testclient import TestClient

from app.league import main
from tests.login import log_in


def league(*args: str) -> int:
    return main(list(args))


def club_id_in(output: str) -> str:
    """The club's number as the command printed it: "… (№ 3)"."""
    return output.rsplit("№ ", 1)[1].split(")", 1)[0]


def test_a_new_clubs_appointed_owner_logs_in_and_sees_their_club(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert league("create-club", "Покер-клуб «Томь»", "--primary", "#1F5C4A", "--accent", "#D9B44A") == 0
    club_id = club_id_in(capsys.readouterr().out)

    assert league("appoint-owner", club_id, "Наталья Широкова", "+7 999 000-00-13") == 0

    log_in(client, caplog, "+79990000013")
    me = client.get("/api/auth/me").json()
    assert (me["admin"]["name"], me["admin"]["role"]) == ("Наталья Широкова", "owner")
    assert me["club"] == {
        "id": int(club_id),
        "name": "Покер-клуб «Томь»",
        "logo_url": "/logos/league.svg",
        "primary_color": "#1F5C4A",
        "accent_color": "#D9B44A",
    }


def test_the_leagues_changes_are_in_the_clubs_log_as_done_by_the_league(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    league("create-club", "Покер-клуб «Томь»")
    club_id = club_id_in(capsys.readouterr().out)

    league("appoint-owner", club_id, "Наталья Широкова", "+7 999 000-00-13")

    log_in(client, caplog, "+79990000013")
    log = client.get(f"/api/clubs/{club_id}/log").json()
    assert [(e["action"], e["admin"], e["by_league"], e["details"]) for e in log] == [
        ("owner_appointed", None, True, "Наталья Широкова, +7 999 000-00-13")
    ]


def test_a_renamed_club_is_shown_under_its_new_name_and_the_rename_is_logged(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    league("create-club", "Покер-клуб «Томь»")
    club_id = club_id_in(capsys.readouterr().out)
    league("appoint-owner", club_id, "Наталья Широкова", "+7 999 000-00-13")

    assert league("rename-club", club_id, "Покер-клуб «Томь-Арена»") == 0

    log_in(client, caplog, "+79990000013")
    assert client.get("/api/auth/me").json()["club"]["name"] == "Покер-клуб «Томь-Арена»"
    latest = client.get(f"/api/clubs/{club_id}/log").json()[0]
    assert (latest["action"], latest["by_league"], latest["details"]) == (
        "club_renamed",
        True,
        "Покер-клуб «Томь» → Покер-клуб «Томь-Арена»",
    )


def test_a_dismissed_owner_is_logged_out_at_once_and_the_dismissal_is_logged(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    league("create-club", "Покер-клуб «Томь»")
    club_id = club_id_in(capsys.readouterr().out)
    league("appoint-owner", club_id, "Наталья Широкова", "+7 999 000-00-13")
    league("appoint-owner", club_id, "Пётр Широков", "+7 999 000-00-14")
    log_in(client, caplog, "+79990000013")

    assert league("dismiss-owner", "+7 999 000-00-13") == 0

    assert client.get("/api/auth/me").status_code == 401
    log_in(client, caplog, "+79990000014")
    latest = client.get(f"/api/clubs/{club_id}/log").json()[0]
    assert (latest["action"], latest["by_league"], latest["details"]) == (
        "owner_dismissed",
        True,
        "Наталья Широкова, +7 999 000-00-13",
    )
    assert [m["name"] for m in client.get(f"/api/clubs/{club_id}/team").json()] == ["Пётр Широков"]


def test_the_list_of_clubs_shows_each_with_its_owners(capsys: pytest.CaptureFixture[str]) -> None:
    league("create-club", "Покер-клуб «Томь»", "--primary", "#1F5C4A", "--accent", "#D9B44A")
    tom = club_id_in(capsys.readouterr().out)
    league("create-club", "Покер-клуб «Иртыш»")
    irtysh = club_id_in(capsys.readouterr().out)
    league("appoint-owner", tom, "Наталья Широкова", "+7 999 000-00-13")
    league("appoint-owner", tom, "Пётр Широков", "+7 999 000-00-14")
    league("dismiss-owner", "+7 999 000-00-14")
    capsys.readouterr()

    assert league("clubs") == 0

    assert capsys.readouterr().out == (
        f"№ {tom} Покер-клуб «Томь», цвета #1F5C4A и #D9B44A\n"
        "    владелец: Наталья Широкова, +7 999 000-00-13\n"
        f"№ {irtysh} Покер-клуб «Иртыш», цвета #0F172A и #F59E0B\n"
        "    владельца нет\n"
    )


def test_an_admin_of_the_club_appointed_its_owner_becomes_one(
    client: TestClient,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    league("create-club", "Покер-клуб «Томь»")
    club_id = club_id_in(capsys.readouterr().out)
    league("appoint-owner", club_id, "Наталья Широкова", "+7 999 000-00-13")
    log_in(client, caplog, "+79990000013")
    client.post(f"/api/clubs/{club_id}/team", json={"name": "Павел Громов", "phone": "+79990000003"})
    client.post("/api/auth/logout")

    assert league("appoint-owner", club_id, "Павел Громов", "+7 999 000-00-03") == 0

    log_in(client, caplog, "+79990000003")
    assert client.get("/api/auth/me").json()["admin"]["role"] == "owner"
    assert [(m["name"], m["role"]) for m in client.get(f"/api/clubs/{club_id}/team").json()] == [
        ("Наталья Широкова", "owner"),
        ("Павел Громов", "owner"),
    ]


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        (
            ["appoint-owner", "{tom}", "Анна Соколова", "+7 999 000-00-01"],
            "Этот телефон уже у сотрудника другого клуба лиги",
        ),
        (["appoint-owner", "{tom}", "", "+7 999 000-00-31"], "Укажите имя сотрудника"),
        (["create-club", "Покер-клуб «Обь»"], "Клуб «Покер-клуб «Обь»» уже есть (№ {ob})"),
        (["create-club", "Покер-клуб «Иртыш»", "--primary", "red"], "Цвет red: нужен вид #RRGGBB"),
        (["rename-club", "{tom}", "  "], "Укажите название клуба"),
        (["rename-club", "999", "Покер-клуб «Иртыш»"], "Клуба № 999 нет"),
        (["dismiss-owner", "+7 999 000-00-02"], "Владельца с телефоном +7 999 000-00-02 нет"),
    ],
    ids=[
        "another club's staff",
        "no name",
        "a name taken",
        "not a colour",
        "no club name",
        "no such club",
        "not an owner",
    ],
)
def test_a_refused_command_says_why_and_changes_nothing(
    capsys: pytest.CaptureFixture[str], command: list[str], reason: str
) -> None:
    league("create-club", "Покер-клуб «Обь»")
    ob = club_id_in(capsys.readouterr().out)
    league("appoint-owner", ob, "Анна Соколова", "+7 999 000-00-01")
    league("create-club", "Покер-клуб «Томь»")
    tom = club_id_in(capsys.readouterr().out)
    league("clubs")
    before = capsys.readouterr().out

    exit_code = league(*(part.format(tom=tom, ob=ob) for part in command))

    assert exit_code == 1
    assert reason.format(ob=ob) in capsys.readouterr().err
    league("clubs")
    assert capsys.readouterr().out == before
