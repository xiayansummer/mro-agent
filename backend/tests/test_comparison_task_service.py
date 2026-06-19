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
        if "SELECT id, selected_platforms, search_terms_json, structure_json" in sql:
            draft = self.__class__.drafts.get((params["draft_id"], params["uid"]))
            return FakeResult(draft)

        if "SELECT id FROM comparison_tasks" in sql:
            matches = [
                t for t in self.__class__.tasks.values()
                if t["draft_id"] == params["draft_id"] and t["user_id"] == params["uid"]
            ]
            if matches:
                latest = max(matches, key=lambda t: t["created_at"])
                return FakeResult((latest["id"],))
            return FakeResult()

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
                        _structure_json(),
                    ))
            return FakeResult()

        if "SELECT st.id, st.platform, st.error_json" in sql:
            rows = []
            for subtask in self.__class__.subtasks.values():
                task = self.__class__.tasks[subtask["task_id"]]
                if (
                    subtask["task_id"] == params["task_id"]
                    and task["user_id"] == params["uid"]
                    and subtask["status"] == params["login_required"]
                ):
                    rows.append((subtask["id"], subtask["platform"], subtask["error_json"]))
            return FakeResult(rows=rows)

        if "SELECT d.structure_json" in sql:
            subtask = self.__class__.subtasks.get(params["subtask_id"])
            if not subtask:
                return FakeResult()
            task = self.__class__.tasks[subtask["task_id"]]
            if task["user_id"] != params["uid"]:
                return FakeResult()
            return FakeResult((_structure_json(),))

        if "UPDATE comparison_subtasks st" in sql and "JOIN comparison_tasks" in sql:
            subtask = self.__class__.subtasks.get(params.get("subtask_id"))
            if not subtask and "task_id" in params:
                subtask = next(
                    (
                        item
                        for item in self.__class__.subtasks.values()
                        if item["task_id"] == params["task_id"]
                        and item["platform"] == params["platform"]
                    ),
                    None,
                )
            if not subtask:
                return FakeResult(rowcount=0)
            task = self.__class__.tasks[subtask["task_id"]]
            if task["user_id"] != params["uid"]:
                return FakeResult(rowcount=0)
            if "st.platform = :platform" in sql and subtask["platform"] != params["platform"]:
                return FakeResult(rowcount=0)
            if "st.status IN" in sql and subtask["status"] not in {
                params["login_required"],
                params["failed"],
                params["timeout"],
            }:
                return FakeResult(rowcount=0)
            subtask["status"] = params.get("status", params.get("queued"))
            subtask["error_json"] = params.get("error_json")
            subtask["items_json"] = params.get("items_json")
            subtask["leased_until"] = None
            return FakeResult(rowcount=1)

        if "SELECT task_id FROM comparison_subtasks" in sql:
            subtask = self.__class__.subtasks.get(params["subtask_id"])
            return FakeResult((subtask["task_id"],) if subtask else None)

        if "SELECT status, COUNT(*)" in sql:
            counts = {}
            for subtask in self.__class__.subtasks.values():
                if subtask["task_id"] == params["task_id"]:
                    counts[subtask["status"]] = counts.get(subtask["status"], 0) + 1
            return FakeResult(rows=list(counts.items()))

        if "UPDATE comparison_subtasks" in sql:
            if "subtask_id" in params:
                subtask = self.__class__.subtasks.get(params["subtask_id"])
                if not subtask:
                    return FakeResult(rowcount=0)
                subtask["status"] = params["queued"]
                subtask["items_json"] = None
                subtask["error_json"] = None
                subtask["leased_until"] = None
                return FakeResult(rowcount=1)
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

        if "UPDATE comparison_tasks" in sql and "completed_at" in sql:
            task = self.__class__.tasks[params["task_id"]]
            if task["user_id"] != params.get("uid", task["user_id"]):
                return FakeResult(rowcount=0)
            task["status"] = params["status"]
            task["completed_at"] = params.get("completed_at")
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


def _structure_json(brand=None):
    return json.dumps({
        "category": {"l3": "六角头螺栓", "confidence": 0.8, "alternatives": []},
        "specification": {
            "productType": "外六角螺栓",
            "brand": brand,
            "model": None,
            "material": "304",
            "size": "M8",
            "standard": None,
            "attributes": [{"name": "规格", "value": "M8"}],
            "missing": [],
        },
        "purchaseConstraints": {"preferredPlatforms": ["jd"]},
        "searchTerms": {"jd": ["外六角螺栓 304 M8"], "zkh": []},
    })


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    FakeSession.drafts = {
        ("draft-1", 7): (
            "draft-1",
            json.dumps(["jd", "zkh"]),
            json.dumps({"jd": ["jd term"], "zkh": ["zkh term"]}),
            _structure_json(),
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
async def test_start_draft_reuses_existing_task_no_duplicate(monkeypatch):
    """同一草稿重复 start(双击 / 重试)应复用已有 task,不建第二套子任务。"""
    async def fake_status(user_id):
        return ExtensionStatus(online=True, platforms=[PlatformStatus(platform="jd", loggedIn=True)])

    monkeypatch.setattr(comparison_task_service.extension_service, "get_extension_status", fake_status)
    FakeSession.tasks["task-existing"] = {
        "id": "task-existing", "draft_id": "draft-1", "user_id": 7,
        "status": "queued", "created_at": datetime(2026, 1, 1), "completed_at": None,
    }
    FakeSession.subtasks["sub-existing"] = {
        "id": "sub-existing", "task_id": "task-existing", "platform": "jd",
        "status": "queued", "search_terms_json": json.dumps(["t"]), "items_json": None,
        "error_json": None, "leased_until": None,
        "created_at": datetime(2026, 1, 1), "updated_at": datetime(2026, 1, 1),
    }

    task = await comparison_task_service.start_draft("draft-1", "u7")

    assert task["id"] == "task-existing"  # 复用,未建新 task
    assert len([t for t in FakeSession.tasks.values() if t["draft_id"] == "draft-1"]) == 1


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
    assert leased["requiredBrand"] == ""
    assert FakeSession.subtasks["subtask-1"]["status"] == "in_progress"
    assert FakeSession.tasks["task-1"]["status"] == "running"


@pytest.mark.asyncio
async def test_get_task_requeues_heartbeat_login_required_after_status_report(monkeypatch):
    FakeSession.tasks["task-1"] = {
        "id": "task-1",
        "draft_id": "draft-1",
        "user_id": 7,
        "status": "partial",
        "created_at": datetime(2026, 1, 1),
        "completed_at": None,
    }
    FakeSession.subtasks["subtask-1"] = {
        "id": "subtask-1",
        "task_id": "task-1",
        "platform": "jd",
        "status": "login_required",
        "search_terms_json": json.dumps(["jd term"]),
        "items_json": None,
        "error_json": json.dumps({"code": "login_required", "message": "平台未登录或登录态未知"}),
        "leased_until": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }

    async def fake_status(user_id):
        return ExtensionStatus(
            online=True,
            platforms=[PlatformStatus(platform="jd", loggedIn=True)],
        )

    monkeypatch.setattr(comparison_task_service.extension_service, "get_extension_status", fake_status)

    task = await comparison_task_service.get_task("task-1", "u7")

    assert task["status"] == "queued"
    assert task["subtasks"][0]["status"] == "queued"
    assert task["subtasks"][0]["error"] is None
    assert FakeSession.tasks["task-1"]["status"] == "queued"


@pytest.mark.asyncio
async def test_get_task_requeues_zkh_when_status_is_unknown(monkeypatch):
    FakeSession.tasks["task-1"] = {
        "id": "task-1",
        "draft_id": "draft-1",
        "user_id": 7,
        "status": "partial",
        "created_at": datetime(2026, 1, 1),
        "completed_at": None,
    }
    FakeSession.subtasks["subtask-1"] = {
        "id": "subtask-1",
        "task_id": "task-1",
        "platform": "zkh",
        "status": "login_required",
        "search_terms_json": json.dumps(["zkh term"]),
        "items_json": None,
        "error_json": json.dumps({"code": "login_required", "message": "平台未登录或登录态未知"}),
        "leased_until": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }

    async def fake_status(user_id):
        return ExtensionStatus(
            online=True,
            platforms=[PlatformStatus(platform="zkh", loggedIn=None)],
        )

    monkeypatch.setattr(comparison_task_service.extension_service, "get_extension_status", fake_status)

    task = await comparison_task_service.get_task("task-1", "u7")

    assert task["status"] == "queued"
    assert task["subtasks"][0]["status"] == "queued"


@pytest.mark.asyncio
async def test_get_task_does_not_requeue_verification_failure(monkeypatch):
    FakeSession.tasks["task-1"] = {
        "id": "task-1",
        "draft_id": "draft-1",
        "user_id": 7,
        "status": "partial",
        "created_at": datetime(2026, 1, 1),
        "completed_at": None,
    }
    FakeSession.subtasks["subtask-1"] = {
        "id": "subtask-1",
        "task_id": "task-1",
        "platform": "jd",
        "status": "login_required",
        "search_terms_json": json.dumps(["jd term"]),
        "items_json": None,
        "error_json": json.dumps({"message": "京东触发安全验证"}),
        "leased_until": None,
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }

    async def fail_if_called(user_id):
        raise AssertionError("extension status should not be checked")

    monkeypatch.setattr(comparison_task_service.extension_service, "get_extension_status", fail_if_called)

    task = await comparison_task_service.get_task("task-1", "u7")

    assert task["status"] == "partial"
    assert task["subtasks"][0]["status"] == "login_required"


def test_required_brand_from_structure_reads_spec_brand():
    assert comparison_task_service._required_brand_from_structure(_structure_json("美和")) == "美和"
    assert comparison_task_service._required_brand_from_structure(_structure_json()) == ""


@pytest.mark.asyncio
async def test_submit_subtask_results_scopes_by_extension_user(monkeypatch):
    _seed_running_subtask()

    async def fake_session(token):
        return {"userId": 7}

    monkeypatch.setattr(comparison_task_service.extension_service, "get_session_by_token", fake_session)

    ok = await comparison_task_service.submit_subtask_results(
        "token",
        "subtask-1",
        "jd",
        "jd term",
        [{"id": "offer-1", "platform": "jd", "title": "304不锈钢外六角螺栓 M8"}],
    )

    assert ok is True
    assert FakeSession.subtasks["subtask-1"]["status"] == "done"
    item = json.loads(FakeSession.subtasks["subtask-1"]["items_json"])[0]
    assert item["selectedSearchTerm"] == "jd term"
    assert item["matchScore"] > 0
    assert item["matchReasons"]
    assert FakeSession.tasks["task-1"]["status"] == "done"
    assert FakeSession.tasks["task-1"]["completed_at"] is not None


@pytest.mark.asyncio
async def test_update_subtask_status_rejects_wrong_user(monkeypatch):
    _seed_running_subtask()

    async def fake_session(token):
        return {"userId": 8}

    monkeypatch.setattr(comparison_task_service.extension_service, "get_session_by_token", fake_session)

    ok = await comparison_task_service.update_subtask_status("token", "subtask-1", "failed", "boom")

    assert ok is False
    assert FakeSession.subtasks["subtask-1"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_retry_subtask_requeues_failed_platform():
    _seed_running_subtask()
    FakeSession.tasks["task-1"]["status"] = "partial"
    FakeSession.tasks["task-1"]["completed_at"] = datetime(2026, 1, 1, 0, 2)
    FakeSession.subtasks["subtask-1"]["status"] = "failed"
    FakeSession.subtasks["subtask-1"]["items_json"] = json.dumps([{"id": "old"}])
    FakeSession.subtasks["subtask-1"]["error_json"] = json.dumps({"message": "boom"})

    task = await comparison_task_service.retry_subtask("task-1", "jd", "u7")

    assert task["status"] == "queued"
    assert task["subtasks"][0]["status"] == "queued"
    assert task["subtasks"][0]["items"] == []
    assert task["subtasks"][0]["error"] is None
    assert FakeSession.tasks["task-1"]["completed_at"] is None


@pytest.mark.asyncio
async def test_get_latest_session_offers_flattens_items(monkeypatch):
    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params):
            assert "chat_session_id" in str(statement)
            return FakeResult(("task-1",))
    monkeypatch.setattr(comparison_task_service, "AsyncSessionLocal", S)
    monkeypatch.setattr(comparison_task_service, "_require_db_user_id", lambda u: 7)

    async def fake_get_task(task_id, user_id):
        assert task_id == "task-1"
        return {"id": "task-1", "subtasks": [
            {"platform": "jd",  "items": [{"id": "a", "priceValue": 1}]},
            {"platform": "zkh", "items": [{"id": "b", "priceValue": 2}]},
        ]}
    monkeypatch.setattr(comparison_task_service, "get_task", fake_get_task)

    offers = await comparison_task_service.get_latest_session_offers("sess-1", "u7")
    assert [o["id"] for o in offers] == ["a", "b"]


@pytest.mark.asyncio
async def test_get_latest_session_offers_none_when_no_task(monkeypatch):
    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params): return FakeResult(None)
    monkeypatch.setattr(comparison_task_service, "AsyncSessionLocal", S)
    monkeypatch.setattr(comparison_task_service, "_require_db_user_id", lambda u: 7)
    assert await comparison_task_service.get_latest_session_offers("sess-x", "u7") is None


@pytest.mark.asyncio
async def test_ehsy_search_term_prefers_jd_then_zkh_then_producttype():
    from app.services.comparison_task_service import _ehsy_search_term
    assert _ehsy_search_term({"jd": ["a", "b"], "zkh": ["c"]}, {}) == "a"
    assert _ehsy_search_term({"jd": [], "zkh": ["c"]}, {}) == "c"
    assert _ehsy_search_term({}, {"specification": {"productType": "口罩"}}) == "口罩"


@pytest.mark.asyncio
async def test_inject_ehsy_inserts_done_subtask(monkeypatch):
    from app.services import comparison_task_service as svc

    captured = {}

    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params):
            if "INSERT INTO comparison_subtasks" in str(statement):
                captured.update(params)
            return FakeResult()
        async def commit(self): pass
    monkeypatch.setattr(svc, "AsyncSessionLocal", S)

    async def fake_fetch(term, limit=8):
        return [{"id": "ehsy-1", "platform": "ehsy", "priceValue": 4.0, "title": "口罩"}]
    monkeypatch.setattr(svc.ehsy_comparison_source, "fetch_ehsy_offers", fake_fetch)
    monkeypatch.setattr(svc, "rank_external_offers", lambda s, o, preferences=None: o)
    async def fake_prefs(uid): return {}
    monkeypatch.setattr(svc.memory_service, "get_preference_signals", fake_prefs)
    async def fake_refresh(session, sid): return None
    monkeypatch.setattr(svc, "_refresh_task_status", fake_refresh)

    await svc._inject_ehsy_subtask("task-1", "u7", {"specification": {"productType": "口罩"}}, {"jd": ["口罩"]})

    assert captured.get("platform") == "ehsy"
    assert captured.get("status") == svc.ComparisonSubtaskStatus.DONE.value
    assert "口罩" in captured.get("items_json", "")


@pytest.mark.asyncio
async def test_inject_ehsy_swallows_failure(monkeypatch):
    from app.services import comparison_task_service as svc
    inserted = {"n": 0}

    class S:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def execute(self, statement, params):
            inserted["n"] += 1
            return FakeResult()
        async def commit(self): pass
    monkeypatch.setattr(svc, "AsyncSessionLocal", S)

    async def boom(term, limit=8):
        raise RuntimeError("ehsy down")
    monkeypatch.setattr(svc.ehsy_comparison_source, "fetch_ehsy_offers", boom)

    # 不抛异常,且没有 INSERT
    await svc._inject_ehsy_subtask("task-1", "u7", {}, {"jd": ["口罩"]})
    assert inserted["n"] == 0


@pytest.mark.asyncio
async def test_start_draft_calls_inject_ehsy_when_ehsy_in_platforms(monkeypatch):
    """接线保护：selected_platforms 含 ehsy 时 start_draft 必须调用 _inject_ehsy_subtask。

    spy 记录调用参数；如有人删掉 start_draft 里的 ehsy 调用点，本测试即刻红灯。
    """
    # 在 fake_db 已有的 ("draft-1", 7) 旁边，再注入一条含 ehsy 的草稿。
    FakeSession.drafts[("draft-ehsy", 7)] = (
        "draft-ehsy",
        json.dumps(["jd", "zkh", "ehsy"]),
        json.dumps({"jd": ["螺栓 M8"], "zkh": ["螺栓 M8"]}),
        _structure_json(),
    )

    async def fake_status(user_id):
        return ExtensionStatus(
            online=True,
            platforms=[
                PlatformStatus(platform="jd", loggedIn=True),
                PlatformStatus(platform="zkh", loggedIn=True),
            ],
        )

    monkeypatch.setattr(comparison_task_service.extension_service, "get_extension_status", fake_status)

    injected_calls: list[dict] = []

    async def spy_inject(task_id, user_id, structure, search_terms):
        injected_calls.append({"task_id": task_id, "user_id": user_id, "search_terms": search_terms})

    monkeypatch.setattr(comparison_task_service, "_inject_ehsy_subtask", spy_inject)

    task = await comparison_task_service.start_draft("draft-ehsy", "u7")

    assert task is not None, "start_draft 应返回 task dict"
    assert len(injected_calls) == 1, f"_inject_ehsy_subtask 应被调用一次，实际 {len(injected_calls)} 次"
    assert injected_calls[0]["task_id"] == task["id"]
    assert injected_calls[0]["search_terms"] == {"jd": ["螺栓 M8"], "zkh": ["螺栓 M8"]}


def _seed_running_subtask():
    FakeSession.tasks["task-1"] = {
        "id": "task-1",
        "draft_id": "draft-1",
        "user_id": 7,
        "status": "running",
        "created_at": datetime(2026, 1, 1),
        "completed_at": None,
    }
    FakeSession.subtasks["subtask-1"] = {
        "id": "subtask-1",
        "task_id": "task-1",
        "platform": "jd",
        "status": "in_progress",
        "search_terms_json": json.dumps(["jd term"]),
        "items_json": None,
        "error_json": None,
        "leased_until": datetime(2026, 1, 1, 0, 1),
        "created_at": datetime(2026, 1, 1),
        "updated_at": datetime(2026, 1, 1),
    }
