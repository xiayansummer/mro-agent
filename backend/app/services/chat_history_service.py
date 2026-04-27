"""
Server-side chat history persistence.

Sessions and messages are scoped per user via user_id (the external 'u{db_id}' form).
Anonymous users no longer exist in the product, so user_id can be assumed to map to t_user.

Each user keeps at most MAX_SESSIONS_PER_USER recent sessions; older ones are auto-deleted.
"""
import json
import logging
from typing import Optional

from sqlalchemy import text

from app.db.mysql import AsyncSessionLocal
from app.services.user_service import _external_id_to_db_id

logger = logging.getLogger(__name__)

MAX_SESSIONS_PER_USER = 200
TITLE_MAX_LEN = 60


def _derive_title(first_user_msg: str) -> str:
    txt = (first_user_msg or "").strip().replace("\n", " ")
    if len(txt) > 20:
        txt = txt[:20] + "…"
    return txt or "新对话"


async def list_sessions(user_id: str) -> list[dict]:
    db_id = _external_id_to_db_id(user_id)
    if db_id is None:
        return []
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            text(
                "SELECT id, title, created_at, updated_at "
                "FROM t_chat_session WHERE user_id = :uid "
                "ORDER BY updated_at DESC LIMIT :lim"
            ),
            {"uid": db_id, "lim": MAX_SESSIONS_PER_USER},
        )
        return [
            {
                "id": row[0],
                "title": row[1],
                "createdAt": int(row[2].timestamp() * 1000) if row[2] else 0,
                "updatedAt": int(row[3].timestamp() * 1000) if row[3] else 0,
            }
            for row in r.fetchall()
        ]


async def get_session(session_id: str, user_id: str) -> Optional[dict]:
    db_id = _external_id_to_db_id(user_id)
    if db_id is None:
        return None
    async with AsyncSessionLocal() as s:
        r = await s.execute(
            text("SELECT id, title, created_at, updated_at FROM t_chat_session WHERE id = :id AND user_id = :uid"),
            {"id": session_id, "uid": db_id},
        )
        row = r.fetchone()
        if not row:
            return None

        msgs_r = await s.execute(
            text(
                "SELECT id, role, content, image_data, sku_results, competitor_results "
                "FROM t_chat_message WHERE session_id = :sid ORDER BY id"
            ),
            {"sid": session_id},
        )
        messages = []
        for m in msgs_r.fetchall():
            sku_results = json.loads(m[4]) if m[4] else None
            comp_results = json.loads(m[5]) if m[5] else None
            messages.append({
                "id": str(m[0]),
                "role": m[1],
                "content": m[2] or "",
                "imageUrl": m[3] or None,
                "skuResults": sku_results,
                "competitorResults": comp_results,
            })

        return {
            "id": row[0],
            "title": row[1],
            "createdAt": int(row[2].timestamp() * 1000) if row[2] else 0,
            "updatedAt": int(row[3].timestamp() * 1000) if row[3] else 0,
            "messages": messages,
        }


async def delete_session(session_id: str, user_id: str) -> bool:
    db_id = _external_id_to_db_id(user_id)
    if db_id is None:
        return False
    async with AsyncSessionLocal() as s:
        # Verify ownership before delete
        r = await s.execute(
            text("SELECT 1 FROM t_chat_session WHERE id = :id AND user_id = :uid"),
            {"id": session_id, "uid": db_id},
        )
        if not r.fetchone():
            return False
        await s.execute(text("DELETE FROM t_chat_message WHERE session_id = :sid"), {"sid": session_id})
        await s.execute(text("DELETE FROM t_chat_session WHERE id = :id"), {"id": session_id})
        await s.commit()
        return True


async def update_title(session_id: str, user_id: str, title: str) -> bool:
    db_id = _external_id_to_db_id(user_id)
    if db_id is None:
        return False
    title = (title or "").strip()[:TITLE_MAX_LEN] or "新对话"
    async with AsyncSessionLocal() as s:
        result = await s.execute(
            text("UPDATE t_chat_session SET title = :t WHERE id = :id AND user_id = :uid"),
            {"t": title, "id": session_id, "uid": db_id},
        )
        await s.commit()
        return result.rowcount > 0


async def save_turn(
    session_id: str,
    user_id: str,
    user_message: str,
    image_b64: str,
    assistant_text: str,
    sku_results: Optional[list],
    competitor_results: Optional[list],
) -> None:
    """
    Save one user/assistant turn. Creates the session row if needed; updates title from
    first user message; trims oldest sessions over MAX_SESSIONS_PER_USER.
    Fire-and-forget — failures logged but not raised.
    """
    db_id = _external_id_to_db_id(user_id)
    if db_id is None:
        return

    try:
        async with AsyncSessionLocal() as s:
            # Upsert session
            r = await s.execute(
                text("SELECT id, title FROM t_chat_session WHERE id = :id"),
                {"id": session_id},
            )
            existing = r.fetchone()
            if existing is None:
                await s.execute(
                    text(
                        "INSERT INTO t_chat_session (id, user_id, title) "
                        "VALUES (:id, :uid, :title)"
                    ),
                    {"id": session_id, "uid": db_id, "title": _derive_title(user_message)},
                )
            else:
                # Touch updated_at; title only updated if still the default
                if existing[1] == "新对话" and user_message:
                    await s.execute(
                        text("UPDATE t_chat_session SET title = :t, updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                        {"t": _derive_title(user_message), "id": session_id},
                    )
                else:
                    await s.execute(
                        text("UPDATE t_chat_session SET updated_at = CURRENT_TIMESTAMP WHERE id = :id"),
                        {"id": session_id},
                    )

            # Insert user message
            await s.execute(
                text(
                    "INSERT INTO t_chat_message (session_id, role, content, image_data) "
                    "VALUES (:sid, 'user', :content, :img)"
                ),
                {"sid": session_id, "content": user_message, "img": image_b64 or None},
            )

            # Insert assistant message
            await s.execute(
                text(
                    "INSERT INTO t_chat_message (session_id, role, content, sku_results, competitor_results) "
                    "VALUES (:sid, 'assistant', :content, :sku, :comp)"
                ),
                {
                    "sid": session_id,
                    "content": assistant_text,
                    "sku": json.dumps(sku_results, ensure_ascii=False) if sku_results else None,
                    "comp": json.dumps(competitor_results, ensure_ascii=False) if competitor_results else None,
                },
            )

            await s.commit()

        # Trim old sessions in a separate transaction
        await _trim_old_sessions(db_id)

    except Exception as e:
        logger.error(f"chat_history.save_turn failed for user {user_id}: {e}", exc_info=True)


async def _trim_old_sessions(db_id: int) -> None:
    """Delete sessions beyond MAX_SESSIONS_PER_USER, oldest first."""
    async with AsyncSessionLocal() as s:
        # Find session ids beyond the cap
        r = await s.execute(
            text(
                "SELECT id FROM t_chat_session WHERE user_id = :uid "
                "ORDER BY updated_at DESC LIMIT :off, 1000"
            ),
            {"uid": db_id, "off": MAX_SESSIONS_PER_USER},
        )
        old_ids = [row[0] for row in r.fetchall()]
        if not old_ids:
            return
        # Delete in batch
        placeholders = ", ".join(f":id{i}" for i in range(len(old_ids)))
        params = {f"id{i}": sid for i, sid in enumerate(old_ids)}
        await s.execute(text(f"DELETE FROM t_chat_message WHERE session_id IN ({placeholders})"), params)
        await s.execute(text(f"DELETE FROM t_chat_session WHERE id IN ({placeholders})"), params)
        await s.commit()
        logger.info(f"chat_history: trimmed {len(old_ids)} old sessions for user db_id={db_id}")
