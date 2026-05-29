from fastapi.testclient import TestClient

from app.main import app
from app.models.comparison import ExtensionStatus
from app.routers.auth import require_user_id
from app.routers.comparison import comparison_task_service, extension_service


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


def test_comparison_extension_status_returns_default_when_authenticated(monkeypatch):
    async def fake_get_extension_status(user_id):
        return ExtensionStatus()

    monkeypatch.setattr(extension_service, "get_extension_status", fake_get_extension_status)
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


def test_extension_task_poll_returns_204_when_no_task(monkeypatch):
    async def fake_lease_next_subtask(token):
        assert token == "extension-token"
        return None

    monkeypatch.setattr(comparison_task_service, "lease_next_subtask", fake_lease_next_subtask)
    client = TestClient(app)

    response = client.get(
        "/api/extension/tasks/next",
        headers={"X-Extension-Token": "extension-token"},
    )

    assert response.status_code == 204


def test_start_draft_route_returns_task(monkeypatch):
    async def fake_start_draft(draft_id, user_id):
        assert draft_id == "draft-1"
        assert user_id == "u1"
        return {"id": "task-1", "draftId": "draft-1", "status": "queued", "subtasks": []}

    monkeypatch.setattr(comparison_task_service, "start_draft", fake_start_draft)
    app.dependency_overrides[require_user_id] = lambda: "u1"
    client = TestClient(app)
    try:
        response = client.post("/api/comparison/drafts/draft-1/start")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["id"] == "task-1"


def test_retry_task_platform_route_returns_task(monkeypatch):
    async def fake_retry_subtask(task_id, platform, user_id):
        assert task_id == "task-1"
        assert platform == "jd"
        assert user_id == "u1"
        return {"id": "task-1", "draftId": "draft-1", "status": "queued", "subtasks": []}

    monkeypatch.setattr(comparison_task_service, "retry_subtask", fake_retry_subtask)
    app.dependency_overrides[require_user_id] = lambda: "u1"
    client = TestClient(app)
    try:
        response = client.post("/api/comparison/tasks/task-1/retry", json={"platform": "jd"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["status"] == "queued"
