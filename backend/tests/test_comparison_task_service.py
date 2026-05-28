import json
from datetime import datetime, timedelta

import pytest

from app.models.comparison import ExtensionStatus, PlatformStatus
from app.services import comparison_task_service


class FakeResult:
    def __init__(self, row=None, rows=None, rowcount=1):
        self._row = row
        self._rows = rows or []
        self.rowcount = rowcount

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class FakeSession:
    drafts = {}
    tasks = {}
    subtasks = {}
    last_draft_status = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, params):
        sql = str(statement)
        if "SELECT id, selected_platforms, search_terms_json" in sql:
            draft = self.__class__.drafts.get((params["draft_id"], params["uid"]))
            return FakeResult(draft)

        if "INSERT INTO comparison_tasks" in sql:
            now = datetime(2026, 1, 1)
            self.__class__.tasks[params["id"]] = {
                "id": params["id"],
                "draft_id": params["draft_id"],
                "user_id": params["uid"],
                "status": params["status"],
                "created_at": now,
                "completed_at": None,
            }
            return FakeResult()

        if "INSERT INTO comparison_subtasks" in sql:
            now = datetime(2026, 1, 1)
            self.__class__.subtasks[params["id"]] = {
                "id": params["id"],
                "task_id": params["task_id"],
                "platform": params["platform"],
                "status": params["status"],
                "search_terms_json": params["search_terms_json"],
                "items_json": None,
                "error_json": params["error_json"],
                "leased_until": None,
                "created_at": now,
                "updated_at": now,
            }
            return FakeResult()

        if "UPDATE comparison_drafts" in sql:
            self.__class__.last_draft_status = params["status"]
            return FakeResult()

        if "SELECT id, draft_id, status" in sql:
            task = self.__class__.tasks.get(params["task_id"])
            if not task or task["user_id"] != params["uid"]:
                return FakeResult()
            return FakeResult((
                task["id"],
                task["draft_id"],
                task["status"],
                task["created_at"],
                task["completed_at"],
            ))

        if "SELECT id, platform, status" in sql:
            rows = [
                _subtask_row(subtask)
                for subtask in self.__class__.subtasks.values()
                if subtask["task_id"] == params["task_id"]
            ]
            return FakeResult(rows=rows)

        if "SELECT st.id, st.task_id" in sql:
            for subtask in self.__class__.subtasks.values():
                task = self.__class__.tasks[subtask["task_id"]]
                lease_expired = subtask["leased_until"] is None or subtask["leased_until"] < params["now"]
                if (
                    task["user_id"] == params["uid"]
                    and subtask["status"] == params["queued"]
                    and lease_expired
                ):
                    return FakeResult((
                        subtask["id"],
                        subtask["task_id"],
                        subtask["platform"],
                        subtask["search_terms_json"],
                    ))
            return FakeResult()

        if "UPDATE comparison_subtasks" in sql:
            subtask = self.__class__.subtasks.get(params["id"])
            if not subtask:
                return FakeResult(rowcount=0)
            lease_expired = subtask["leased_until"] is None or subtask["leased_until"] < params["now"]
            if subtask["status"] != params["queued"] or not lease_expired:
                return FakeResult(rowcount=0)
            subtask["status"] = params["status"]
            subtask["leased_until"] = params["leased_until"]
            return FakeResult(rowcount=1)

        if "UPDATE comparison_tasks SET status" in sql:
            self.__class__.tasks[params["task_id"]]["status"] = params["status"]
            return FakeResult()

        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        return None

    async def rollback(self):
        return None


def _subtask_row(subtask):
    return (
        subtask["id"],
        subtask["platform"],
        subtask["status"],
        subtask["search_terms_json"],
        subtask["items_json"],
        subtask["error_json"],
        subtask["leased_until"],
        subtask["created_at"],
        subtask["updated_at"],
    )


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    FakeSession.drafts = {
        ("draft-1", 7): (
            "draft-1",
            json.dumps(["jd", "zkh"]),
            json.dumps({"jd": ["jd term"], "zkh": ["zkh term"]}),
        )
    }
    FakeSession.tasks = {}
    FakeSession.subtasks = {}
    FakeSession.last_draft_status = None
    monkeypatch.setattr(comparison_task_service, "AsyncSessionLocal", FakeSession)


@pytest.mark.asyncio
async def test_start_draft_creates_queued_and_login_required_subtasks(monkeypatch):
    async def fake_status(user_id):
        return ExtensionStatus(
            online=True,
            platforms=[
                PlatformStatus(platform="jd", loggedIn=True),
                PlatformStatus(platform="zkh", loggedIn=False),
            ],
        )

    monkeypatch.setattr(comparison_task_service.extension_service, "get_extension_status", fake_status)

    task = await comparison_task_service.start_draft("draft-1", "u7")

    assert task["status"] == "queued"
    assert FakeSession.last_draft_status == "task_created"
    by_platform = {item["platform"]: item for item in task["subtasks"]}
    assert by_platform["jd"]["status"] == "queued"
    assert by_platform["zkh"]["status"] == "login_required"
    assert by_platform["zkh"]["error"]["code"] == "login_required"


@pytest.mark.asyncio
async def test_start_draft_blocks_all_subtasks_when_extension_offline(monkeypatch):
    async def fake_status(user_id):
        return ExtensionStatus(online=False, platforms=[])

    monkeypatch.setattr(comparison_task_service.extension_service, "get_extension_status", fake_status)

    task = await comparison_task_service.start_draft("draft-1", "u7")

    assert task["status"] == "partial"
    assert FakeSession.last_draft_status == "needs_login"
    assert all(item["status"] == "login_required" for item in task["subtasks"])


@pytest.mark.asyncio
async def test_lease_next_subtask_returns_204_shape_when_none(monkeypatch):
    async def fake_session(token):
        return {"userId": 7}

    monkeypatch.setattr(comparison_task_service.extension_service, "get_session_by_token", fake_session)

    assert await comparison_task_service.lease_next_subtask("token") is None


@pytest.mark.asyncio
async def test_lease_next_subtask_marks_subtask_in_progress(monkeypatch):
    FakeSession.tasks["task-1"] = {
        "id": "task-1",
        "draft_id": "draft-1",
        "user_id": 7,
        "status": "queued",
        "created_at": datetime(2026, 1, 1),
        "completed_at": None,
    }
    FakeSession.subtasks["subtask-1"] = {
        "id": "subtask-1",
        "task_id": "task-1",
        "platform": "jd",
        "status": "queued",
        "search_terms_json": json.dumps(["jd term"]),
        "items_json": None,
        "error_json": None,
        "leased_until": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }

    async def fake_session(token):
        return {"userId": 7}

    monkeypatch.setattr(comparison_task_service.extension_service, "get_session_by_token", fake_session)

    leased = await comparison_task_service.lease_next_subtask("token")

    assert leased["subtaskId"] == "subtask-1"
    assert leased["platform"] == "jd"
    assert leased["searchTerms"] == ["jd term"]
    assert FakeSession.subtasks["subtask-1"]["status"] == "in_progress"
    assert FakeSession.tasks["task-1"]["status"] == "running"
