import re
import secrets
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mysql import AsyncSessionLocal

_PHONE_RE = re.compile(r"^1[3-9]\d{9}$")


def is_valid_phone(phone: str) -> bool:
    return bool(phone and _PHONE_RE.match(phone))


def _gen_token() -> str:
    return secrets.token_hex(32)


async def get_user_by_token(token: str) -> Optional[dict]:
    if not token:
        return None
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            text("SELECT id, phone, nickname, auth_token FROM t_user WHERE auth_token = :t"),
            {"t": token},
        )
        row = r.fetchone()
        if not row:
            return None
        return {"id": row[0], "phone": row[1], "nickname": row[2], "auth_token": row[3]}


async def get_user_by_phone(phone: str) -> Optional[dict]:
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            text("SELECT id, phone, nickname, auth_token FROM t_user WHERE phone = :p"),
            {"p": phone},
        )
        row = r.fetchone()
        if not row:
            return None
        return {"id": row[0], "phone": row[1], "nickname": row[2], "auth_token": row[3]}


async def register_user(phone: str, nickname: Optional[str]) -> dict:
    """Create a new user. Caller must verify invite token first."""
    token = _gen_token()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "INSERT INTO t_user (phone, nickname, auth_token) "
                "VALUES (:p, :n, :t)"
            ),
            {"p": phone, "n": nickname or None, "t": token},
        )
        await s.commit()
    return await get_user_by_phone(phone)


async def login_user(phone: str) -> Optional[dict]:
    """Refresh auth_token + last_login_at for existing user. Returns updated user or None."""
    user = await get_user_by_phone(phone)
    if not user:
        return None
    new_token = _gen_token()
    async with AsyncSessionLocal() as s:
        await s.execute(
            text(
                "UPDATE t_user SET auth_token = :t, last_login_at = CURRENT_TIMESTAMP "
                "WHERE id = :id"
            ),
            {"t": new_token, "id": user["id"]},
        )
        await s.commit()
    user["auth_token"] = new_token
    return user


def user_to_external_id(user: dict) -> str:
    """Stable id used downstream as user_id (memory keys, etc.)."""
    return f"u{user['id']}"


def _external_id_to_db_id(external_user_id: str) -> Optional[int]:
    """Reverse of user_to_external_id. Returns None for non-user ids (e.g. legacy session ids)."""
    if not external_user_id or not external_user_id.startswith("u"):
        return None
    try:
        return int(external_user_id[1:])
    except ValueError:
        return None


async def increment_session_count(external_user_id: str) -> Optional[int]:
    """
    Atomically +1 on session_count and return the new value.
    Returns None if user_id doesn't map to a real t_user row.
    """
    db_id = _external_id_to_db_id(external_user_id)
    if db_id is None:
        return None
    async with AsyncSessionLocal() as s:
        await s.execute(
            text("UPDATE t_user SET session_count = session_count + 1 WHERE id = :id"),
            {"id": db_id},
        )
        await s.commit()
        r = await s.execute(text("SELECT session_count FROM t_user WHERE id = :id"), {"id": db_id})
        row = r.fetchone()
        return row[0] if row else None
