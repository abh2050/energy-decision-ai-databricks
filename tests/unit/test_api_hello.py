from fastapi.testclient import TestClient

from edip.api.main import app

client = TestClient(app)


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_whoami_without_identity_is_401():
    assert client.get("/whoami").status_code == 401


def test_whoami_with_forwarded_identity_does_not_echo_it():
    r = client.get(
        "/whoami",
        headers={"X-Forwarded-User": "user-123", "X-Forwarded-Email": "someone@example.com"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body == {
        "authenticated": True,
        "user_header_present": True,
        "email_header_present": True,
    }
    assert "example.com" not in r.text
