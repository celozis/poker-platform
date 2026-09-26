import re

import pytest
from fastapi.testclient import TestClient


def code_from_log(caplog: pytest.LogCaptureFixture, phone: str) -> str:
    # In the prototype the login code is written to the backend log instead of an SMS.
    for record in reversed(caplog.records):
        message = record.getMessage()
        if phone in message:
            match = re.search(r"\b(\d{6})\b", message)
            if match:
                return match.group(1)
    raise AssertionError(f"No login code for {phone} in the log")


def request_code(client: TestClient, caplog: pytest.LogCaptureFixture, phone: str) -> str:
    caplog.set_level("INFO")
    response = client.post("/api/auth/request-code", json={"phone": phone})
    assert response.status_code == 204
    return code_from_log(caplog, phone)


def log_in(client: TestClient, caplog: pytest.LogCaptureFixture, phone: str) -> None:
    code = request_code(client, caplog, phone)
    response = client.post("/api/auth/verify-code", json={"phone": phone, "code": code})
    assert response.status_code == 204


def a_different_code(code: str) -> str:
    return f"{(int(code) + 1) % 1_000_000:06d}"
