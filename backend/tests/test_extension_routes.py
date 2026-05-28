from fastapi.testclient import TestClient

from app.main import app
from app.models.comparison import ExtensionStatus
from app.routers.auth import require_user_id
from app.routers import extension


def test_create_pairing_code_requires_web_auth():
    client = TestClient(app)

    response = client.post("/api/extension/pairing-code")

    assert response.status_code == 401


def test_create_pairing_code_returns_code_when_authenticated(monkeypatch):
    async def fake_create_pairing_code(user_id):
        assert user_id == "u1"
        return {"code": "123456", "ttlSeconds": 300, "expiresAt": 1}

    monkeypatch.setattr(extension.extension_service, "create_pairing_code", fake_create_pairing_code)
    app.dependency_overrides[require_user_id] = lambda: "u1"
    client = TestClient(app)
    try:
        response = client.post("/api/extension/pairing-code")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["code"] == "123456"


def test_register_extension_rejects_bad_code(monkeypatch):
    async def fake_register_extension(**kwargs):
        return None

    monkeypatch.setattr(extension.extension_service, "register_extension", fake_register_extension)
    client = TestClient(app)

    response = client.post("/api/extension/register", json={"code": "123456"})

    assert response.status_code == 400


def test_update_extension_status_requires_valid_extension_token(monkeypatch):
    async def fake_update_extension_status(**kwargs):
        return False

    monkeypatch.setattr(extension.extension_service, "update_extension_status", fake_update_extension_status)
    client = TestClient(app)

    response = client.post("/api/extension/status", json={"platforms": []})

    assert response.status_code == 401


def test_get_web_extension_status(monkeypatch):
    async def fake_get_extension_status(user_id):
        assert user_id == "u1"
        return ExtensionStatus(online=True, deviceName="Mac Chrome")

    monkeypatch.setattr(extension.extension_service, "get_extension_status", fake_get_extension_status)
    app.dependency_overrides[require_user_id] = lambda: "u1"
    client = TestClient(app)
    try:
        response = client.get("/api/extension/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["online"] is True
    assert response.json()["deviceName"] == "Mac Chrome"


def test_extension_next_task_returns_lease(monkeypatch):
    async def fake_lease_next_subtask(token):
        assert token == "extension-token"
        return {
            "subtaskId": "subtask-1",
            "taskId": "task-1",
            "platform": "jd",
            "searchTerms": ["term"],
            "leasedUntil": 1,
        }

    monkeypatch.setattr(extension.comparison_task_service, "lease_next_subtask", fake_lease_next_subtask)
    client = TestClient(app)

    response = client.get(
        "/api/extension/tasks/next",
        headers={"X-Extension-Token": "extension-token"},
    )

    assert response.status_code == 200
    assert response.json()["subtaskId"] == "subtask-1"


def test_extension_update_subtask_status(monkeypatch):
    async def fake_update_subtask_status(**kwargs):
        assert kwargs == {
            "ext_token": "extension-token",
            "subtask_id": "subtask-1",
            "status": "failed",
            "message": "boom",
        }
        return True

    monkeypatch.setattr(extension.comparison_task_service, "update_subtask_status", fake_update_subtask_status)
    client = TestClient(app)

    response = client.post(
        "/api/extension/subtasks/subtask-1/status",
        headers={"X-Extension-Token": "extension-token"},
        json={"status": "failed", "message": "boom"},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_extension_submit_subtask_results(monkeypatch):
    async def fake_submit_subtask_results(**kwargs):
        assert kwargs["ext_token"] == "extension-token"
        assert kwargs["subtask_id"] == "subtask-1"
        assert kwargs["platform"] == "jd"
        assert kwargs["search_term"] == "term"
        assert kwargs["offers"][0]["id"] == "offer-1"
        return True

    monkeypatch.setattr(extension.comparison_task_service, "submit_subtask_results", fake_submit_subtask_results)
    client = TestClient(app)

    response = client.post(
        "/api/extension/subtasks/subtask-1/results",
        headers={"X-Extension-Token": "extension-token"},
        json={
            "platform": "jd",
            "searchTerm": "term",
            "offers": [
                {
                    "id": "offer-1",
                    "platform": "jd",
                    "title": "商品",
                    "productUrl": "https://item.jd.com/1.html",
                    "rawRank": 1,
                    "unitComparable": False,
                    "matchScore": 0,
                }
            ],
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
