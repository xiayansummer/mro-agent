import hashlib
import json
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.db.mysql import AsyncSessionLocal
from app.models.comparison import ExtensionStatus, PlatformStatus
from app.services.user_service import _external_id_to_db_id

PAIRING_CODE_TTL_MINUTES = 5
EXTENSION_OFFLINE_AFTER_SECONDS = 90


def _hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _generate_pairing_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def _generate_ext_token() -> str:
    return secrets.token_urlsafe(32)


async def create_pairing_code(user_id: str) -> dict:
    db_user_id = _require_db_user_id(user_id)
    code = _generate_pairing_code()
    expires_at = datetime.utcnow() + timedelta(minutes=PAIRING_CODE_TTL_MINUTES)

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO extension_pairing_codes (code_hash, user_id, expires_at)
                VALUES (:code_hash, :uid, :expires_at)
                """
            ),
            {
                "code_hash": _hash_secret(code),
                "uid": db_user_id,
                "expires_at": expires_at,
            },
        )
        await session.commit()

    return {
        "code": code,
        "expiresAt": int(expires_at.timestamp() * 1000),
        "ttlSeconds": PAIRING_CODE_TTL_MINUTES * 60,
    }


async def register_extension(
    code: str,
    device_name: Optional[str] = None,
    version: Optional[str] = None,
) -> Optional[dict]:
    code_hash = _hash_secret(code)
    session_id = _new_id("ext")
    ext_token = _generate_ext_token()
    status = ExtensionStatus(
        online=True,
        deviceName=device_name,
        version=version,
        platforms=[],
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT user_id
                FROM extension_pairing_codes
                WHERE code_hash = :code_hash
                  AND used_at IS NULL
                  AND expires_at > :now
                """
            ),
            {"code_hash": code_hash, "now": datetime.utcnow()},
        )
        row = result.fetchone()
        if not row:
            return None

        db_user_id = int(row[0])
        await session.execute(
            text("UPDATE extension_sessions SET active = FALSE WHERE user_id = :uid AND active = TRUE"),
            {"uid": db_user_id},
        )
        await session.execute(
            text("UPDATE extension_pairing_codes SET used_at = :now WHERE code_hash = :code_hash"),
            {"now": datetime.utcnow(), "code_hash": code_hash},
        )
        await session.execute(
            text(
                """
                INSERT INTO extension_sessions (
                    id, user_id, ext_token_hash, device_name, browser,
                    active, status_json, last_seen_at
                ) VALUES (
                    :id, :uid, :token_hash, :device_name, 'chrome',
                    TRUE, :status_json, :now
                )
                """
            ),
            {
                "id": session_id,
                "uid": db_user_id,
                "token_hash": _hash_secret(ext_token),
                "device_name": device_name,
                "status_json": json.dumps(status.model_dump(mode="json"), ensure_ascii=False),
                "now": datetime.utcnow(),
            },
        )
        await session.commit()

    return {
        "sessionId": session_id,
        "extToken": ext_token,
        "browser": "chrome",
    }


async def update_extension_status(
    ext_token: str,
    device_name: Optional[str] = None,
    version: Optional[str] = None,
    platforms: Optional[list[PlatformStatus]] = None,
) -> bool:
    status = ExtensionStatus(
        online=True,
        deviceName=device_name,
        version=version,
        platforms=platforms or [],
        lastSeenAt=datetime.utcnow().isoformat(),
    )
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE extension_sessions
                SET device_name = COALESCE(:device_name, device_name),
                    status_json = :status_json,
                    last_seen_at = :now
                WHERE ext_token_hash = :token_hash
                  AND active = TRUE
                """
            ),
            {
                "device_name": device_name,
                "status_json": json.dumps(status.model_dump(mode="json"), ensure_ascii=False),
                "now": datetime.utcnow(),
                "token_hash": _hash_secret(ext_token),
            },
        )
        await session.commit()
        return result.rowcount > 0


async def get_extension_status(user_id: str) -> ExtensionStatus:
    db_user_id = _require_db_user_id(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT device_name, status_json, last_seen_at
                FROM extension_sessions
                WHERE user_id = :uid AND active = TRUE
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"uid": db_user_id},
        )
        row = result.fetchone()

    if not row:
        return ExtensionStatus()

    status = _status_from_row(row[0], row[1], row[2])
    status.online = _is_online(row[2])
    status.lastSeenAt = row[2].isoformat() if row[2] else None
    return status


async def is_valid_extension_token(ext_token: str) -> bool:
    if not ext_token:
        return False
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT 1
                FROM extension_sessions
                WHERE ext_token_hash = :token_hash AND active = TRUE
                """
            ),
            {"token_hash": _hash_secret(ext_token)},
        )
        return result.fetchone() is not None


def _status_from_row(device_name: Optional[str], raw_status: Optional[str], last_seen_at) -> ExtensionStatus:
    if raw_status:
        try:
            status = ExtensionStatus.model_validate(json.loads(raw_status))
        except Exception:
            status = ExtensionStatus()
    else:
        status = ExtensionStatus()
    if device_name and not status.deviceName:
        status.deviceName = device_name
    if last_seen_at:
        status.lastSeenAt = last_seen_at.isoformat()
    return status


def _is_online(last_seen_at) -> bool:
    if not last_seen_at:
        return False
    return datetime.utcnow() - last_seen_at <= timedelta(seconds=EXTENSION_OFFLINE_AFTER_SECONDS)


def _require_db_user_id(user_id: str) -> int:
    db_user_id = _external_id_to_db_id(user_id)
    if db_user_id is None:
        raise ValueError("invalid user_id")
    return db_user_id
