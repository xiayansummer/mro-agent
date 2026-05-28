from datetime import datetime, timedelta

import pytest

from app.models.comparison import PlatformStatus
from app.services import extension_service


class FakeResult:
    def __init__(self, row=None, rowcount=1):
        self._row = row
        self.rowcount = rowcount

    def fetchone(self):
        return self._row


class FakeSession:
    pairing_codes = {}
    extension_sessions = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def execute(self, statement, params):
        sql = str(statement)
        if "INSERT INTO extension_pairing_codes" in sql:
            self.__class__.pairing_codes[params["code_hash"]] = {
                "user_id": params["uid"],
                "expires_at": params["expires_at"],
                "used_at": None,
            }
            return FakeResult()

        if "SELECT user_id" in sql and "FROM extension_pairing_codes" in sql:
            row = self.__class__.pairing_codes.get(params["code_hash"])
            if not row or row["used_at"] or row["expires_at"] <= params["now"]:
                return FakeResult()
            return FakeResult((row["user_id"],))

        if "UPDATE extension_sessions SET active = FALSE" in sql:
            for session in self.__class__.extension_sessions.values():
                if session["user_id"] == params["uid"] and session["active"]:
                    session["active"] = False
            return FakeResult()

        if "UPDATE extension_pairing_codes SET used_at" in sql:
            self.__class__.pairing_codes[params["code_hash"]]["used_at"] = params["now"]
            return FakeResult()

        if "INSERT INTO extension_sessions" in sql:
            self.__class__.extension_sessions[params["id"]] = {
                "id": params["id"],
                "user_id": params["uid"],
                "ext_token_hash": params["token_hash"],
                "device_name": params["device_name"],
                "active": True,
                "status_json": params["status_json"],
                "last_seen_at": params["now"],
            }
            return FakeResult()

        if "UPDATE extension_sessions" in sql and "ext_token_hash = :token_hash" in sql:
            for session in self.__class__.extension_sessions.values():
                if session["ext_token_hash"] == params["token_hash"] and session["active"]:
                    session["device_name"] = params["device_name"] or session["device_name"]
                    session["status_json"] = params["status_json"]
                    session["last_seen_at"] = params["now"]
                    return FakeResult(rowcount=1)
            return FakeResult(rowcount=0)

        if "SELECT device_name, status_json, last_seen_at" in sql:
            for session in reversed(list(self.__class__.extension_sessions.values())):
                if session["user_id"] == params["uid"] and session["active"]:
                    return FakeResult((
                        session["device_name"],
                        session["status_json"],
                        session["last_seen_at"],
                    ))
            return FakeResult()

        if "SELECT 1" in sql and "FROM extension_sessions" in sql:
            for session in self.__class__.extension_sessions.values():
                if session["ext_token_hash"] == params["token_hash"] and session["active"]:
                    return FakeResult((1,))
            return FakeResult()

        raise AssertionError(f"unexpected SQL: {sql}")

    async def commit(self):
        return None


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    FakeSession.pairing_codes = {}
    FakeSession.extension_sessions = {}
    monkeypatch.setattr(extension_service, "AsyncSessionLocal", FakeSession)


@pytest.mark.asyncio
async def test_create_pairing_code_stores_hash_only(monkeypatch):
    monkeypatch.setattr(extension_service, "_generate_pairing_code", lambda: "123456")

    result = await extension_service.create_pairing_code("u7")

    assert result["code"] == "123456"
    assert result["ttlSeconds"] == 300
    assert "123456" not in FakeSession.pairing_codes
    assert extension_service._hash_secret("123456") in FakeSession.pairing_codes


@pytest.mark.asyncio
async def test_register_extension_consumes_code_and_deactivates_old_session(monkeypatch):
    monkeypatch.setattr(extension_service, "_generate_pairing_code", lambda: "123456")
    await extension_service.create_pairing_code("u7")
    FakeSession.extension_sessions["old"] = {
        "id": "old",
        "user_id": 7,
        "ext_token_hash": "old_hash",
        "device_name": "old",
        "active": True,
        "status_json": "{}",
        "last_seen_at": datetime.utcnow() - timedelta(seconds=5),
    }

    result = await extension_service.register_extension("123456", "Mac Chrome", "0.1.0")

    assert result is not None
    assert result["extToken"]
    assert FakeSession.extension_sessions["old"]["active"] is False
    active = [s for s in FakeSession.extension_sessions.values() if s["active"]]
    assert len(active) == 1
    assert active[0]["ext_token_hash"] != result["extToken"]
    assert FakeSession.pairing_codes[extension_service._hash_secret("123456")]["used_at"] is not None
    assert await extension_service.register_extension("123456", "Another", "0.1.0") is None


@pytest.mark.asyncio
async def test_update_and_get_extension_status(monkeypatch):
    monkeypatch.setattr(extension_service, "_generate_pairing_code", lambda: "123456")
    await extension_service.create_pairing_code("u7")
    registered = await extension_service.register_extension("123456", "Mac Chrome", "0.1.0")

    ok = await extension_service.update_extension_status(
        registered["extToken"],
        device_name="Mac Chrome",
        version="0.1.1",
        platforms=[PlatformStatus(platform="jd", loggedIn=True)],
    )
    status = await extension_service.get_extension_status("u7")

    assert ok is True
    assert status.online is True
    assert status.deviceName == "Mac Chrome"
    assert status.version == "0.1.1"
    assert status.platforms[0].platform == "jd"
    assert status.platforms[0].loggedIn is True


@pytest.mark.asyncio
async def test_unknown_extension_token_is_invalid():
    assert await extension_service.is_valid_extension_token("missing") is False
