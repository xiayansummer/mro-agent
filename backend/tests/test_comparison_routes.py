from fastapi.testclient import TestClient

from app.main import app
from app.routers.auth import require_user_id


def test_comparison_and_extension_health_are_public():
    client = TestClient(app)

    assert client.get("/api/comparison/health").json() == {"status": "ok"}
    assert client.get("/api/extension/health").json() == {
        "status": "ok",
        "browser": "chrome",
    }


def test_comparison_extension_status_requires_web_auth():
    client = TestClient(app)

    response = client.get("/api/comparison/extension/status")

    assert response.status_code == 401


def test_comparison_extension_status_returns_default_when_authenticated():
    app.dependency_overrides[require_user_id] = lambda: "u1"
    client = TestClient(app)
    try:
        response = client.get("/api/comparison/extension/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "online": False,
        "deviceName": None,
        "version": None,
        "platforms": [],
        "lastSeenAt": None,
    }


def test_comparison_draft_endpoints_auth_gate_before_service():
    client = TestClient(app)
    payload = {
        "sessionId": "s1",
        "message": "M8不锈钢螺栓",
        "structure": {},
    }

    response = client.post("/api/comparison/drafts", json=payload)

    assert response.status_code == 401


def test_extension_task_poll_requires_extension_token():
    client = TestClient(app)

    response = client.get("/api/extension/tasks/next")

    assert response.status_code == 401


def test_extension_task_poll_reaches_service_stub_with_token():
    client = TestClient(app)

    response = client.get(
        "/api/extension/tasks/next",
        headers={"X-Extension-Token": "extension-token"},
    )

    assert response.status_code == 501
