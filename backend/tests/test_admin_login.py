from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from tests.clock import FakeClock
from tests.factories import create_admin, create_club
from tests.login import a_different_code, code_from_log, log_in, request_code


def test_admin_logs_in_with_the_code_from_the_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    club = create_club(name="Покер-клуб «Обь»", primary_color="#0B3D91", accent_color="#F2A900")
    admin = create_admin(club, phone="+79130000001", name="Анна")
    caplog.set_level("INFO")

    requested = client.post("/api/auth/request-code", json={"phone": "+79130000001"})
    assert requested.status_code == 204

    code = code_from_log(caplog, "+79130000001")
    verified = client.post("/api/auth/verify-code", json={"phone": "+79130000001", "code": code})
    assert verified.status_code == 204

    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json() == {
        "admin": {"id": admin.id, "name": "Анна", "phone": "+79130000001"},
        "club": {
            "id": club.id,
            "name": "Покер-клуб «Обь»",
            "logo_url": club.logo_url,
            "primary_color": "#0B3D91",
            "accent_color": "#F2A900",
        },
    }


def test_wrong_code_does_not_log_in(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    create_admin(create_club(), phone="+79130000001")
    code = request_code(client, caplog, "+79130000001")

    verified = client.post(
        "/api/auth/verify-code", json={"phone": "+79130000001", "code": a_different_code(code)}
    )

    assert verified.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_expired_code_does_not_log_in(
    client: TestClient, caplog: pytest.LogCaptureFixture, clock: FakeClock
) -> None:
    create_admin(create_club(), phone="+79130000001")
    code = request_code(client, caplog, "+79130000001")

    clock.advance(timedelta(minutes=6))
    verified = client.post("/api/auth/verify-code", json={"phone": "+79130000001", "code": code})

    assert verified.status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_code_stops_working_after_five_wrong_attempts(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    create_admin(create_club(), phone="+79130000001")
    code = request_code(client, caplog, "+79130000001")
    for _ in range(5):
        client.post(
            "/api/auth/verify-code",
            json={"phone": "+79130000001", "code": a_different_code(code)},
        )

    verified = client.post("/api/auth/verify-code", json={"phone": "+79130000001", "code": code})

    assert verified.status_code == 401


def test_a_new_code_is_sent_at_most_once_a_minute(
    client: TestClient, caplog: pytest.LogCaptureFixture, clock: FakeClock
) -> None:
    # Otherwise re-requesting would reset the wrong-attempt limit and allow brute force.
    create_admin(create_club(), phone="+79130000001")

    def codes_sent() -> int:
        return sum("+79130000001" in record.getMessage() for record in caplog.records)

    request_code(client, caplog, "+79130000001")
    clock.advance(timedelta(seconds=30))
    client.post("/api/auth/request-code", json={"phone": "+79130000001"})
    assert codes_sent() == 1

    clock.advance(timedelta(seconds=31))
    client.post("/api/auth/request-code", json={"phone": "+79130000001"})
    assert codes_sent() == 2


def test_logged_out_session_no_longer_works(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    create_admin(create_club(), phone="+79130000001")
    log_in(client, caplog, "+79130000001")
    token = client.cookies["admin_session"]

    logged_out = client.post("/api/auth/logout")

    assert logged_out.status_code == 204
    assert client.get("/api/auth/me").status_code == 401
    # Even a copy of the old cookie is useless: the session is gone on the server.
    client.cookies.set("admin_session", token)
    assert client.get("/api/auth/me").status_code == 401


def test_admin_can_type_the_phone_in_the_usual_formats(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    create_admin(create_club(), phone="+79130000001")
    caplog.set_level("INFO")

    client.post("/api/auth/request-code", json={"phone": "8 (913) 000-00-01"})
    code = code_from_log(caplog, "+79130000001")
    verified = client.post("/api/auth/verify-code", json={"phone": "+7 913 000 00 01", "code": code})

    assert verified.status_code == 204
