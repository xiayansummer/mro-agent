import json
import uuid
from typing import Optional

from sqlalchemy import text

from app.db.mysql import AsyncSessionLocal
from app.models.comparison import (
    ComparisonDraftStatus,
    ComparisonStructure,
    Platform,
)
from app.services.comparison_query_builder import build_search_terms
from app.services.comparison_structure import build_comparison_structure
from app.services.user_service import _external_id_to_db_id


async def create_draft_from_message(
    user_id: str,
    session_id: str,
    message: str,
    conversation_context: list[dict] | None = None,
    memory_context: str = "",
    image_base64: str = "",
    skip_clarification: bool = False,
) -> dict:
    result = await build_comparison_structure(
        message,
        conversation_context=conversation_context,
        memory_context=memory_context,
        image_base64=image_base64,
        skip_clarification=skip_clarification,
    )
    if not result.shouldCreateDraft or not result.structure:
        return {
            "shouldCreateDraft": False,
            "guidance": result.guidance,
            "slotClarification": result.slotClarification,
            "parsedIntent": result.parsedIntent,
        }
    return {
        "shouldCreateDraft": True,
        "draft": await create_draft(
            user_id=user_id,
            session_id=session_id,
            raw_query=message,
            structure=result.structure,
        ),
        "parsedIntent": result.parsedIntent,
    }


async def create_draft(
    user_id: str,
    session_id: str,
    raw_query: str,
    structure: ComparisonStructure,
) -> dict:
    db_user_id = _require_db_user_id(user_id)
    draft_id = _new_id("cmp_draft")
    structure.searchTerms = build_search_terms(structure)
    selected_platforms = structure.purchaseConstraints.preferredPlatforms or ["jd", "zkh"]

    async with AsyncSessionLocal() as session:
        await session.execute(
            text(
                """
                INSERT INTO comparison_drafts (
                    id, user_id, chat_session_id, raw_query, structure_json,
                    selected_platforms, search_terms_json, status
                ) VALUES (
                    :id, :uid, :sid, :raw_query, :structure_json,
                    :selected_platforms, :search_terms_json, :status
                )
                """
            ),
            {
                "id": draft_id,
                "uid": db_user_id,
                "sid": session_id,
                "raw_query": raw_query,
                "structure_json": _json(structure.model_dump(mode="json")),
                "selected_platforms": _json(selected_platforms),
                "search_terms_json": _json(structure.searchTerms.model_dump(mode="json")),
                "status": ComparisonDraftStatus.NEEDS_CONFIRMATION.value,
            },
        )
        await session.commit()

    draft = await get_draft(draft_id, user_id)
    if draft is None:
        raise RuntimeError("created comparison draft could not be loaded")
    return draft


async def get_draft(draft_id: str, user_id: str) -> Optional[dict]:
    db_user_id = _require_db_user_id(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT id, chat_session_id, raw_query, structure_json, selected_platforms,
                       search_terms_json, platform_status_json, status, created_at, updated_at
                FROM comparison_drafts
                WHERE id = :id AND user_id = :uid
                """
            ),
            {"id": draft_id, "uid": db_user_id},
        )
        row = result.fetchone()
    return _row_to_draft(row) if row else None


async def update_draft_structure(
    draft_id: str,
    user_id: str,
    structure: ComparisonStructure,
    selected_platforms: Optional[list[Platform]] = None,
) -> Optional[dict]:
    db_user_id = _require_db_user_id(user_id)
    structure.searchTerms = build_search_terms(structure)
    platforms = selected_platforms or structure.purchaseConstraints.preferredPlatforms or ["jd", "zkh"]

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE comparison_drafts
                SET structure_json = :structure_json,
                    selected_platforms = :selected_platforms,
                    search_terms_json = :search_terms_json,
                    status = :status
                WHERE id = :id AND user_id = :uid
                """
            ),
            {
                "id": draft_id,
                "uid": db_user_id,
                "structure_json": _json(structure.model_dump(mode="json")),
                "selected_platforms": _json(platforms),
                "search_terms_json": _json(structure.searchTerms.model_dump(mode="json")),
                "status": ComparisonDraftStatus.NEEDS_CONFIRMATION.value,
            },
        )
        await session.commit()

    if result.rowcount <= 0:
        return None
    return await get_draft(draft_id, user_id)


def _row_to_draft(row) -> dict:
    structure = _loads(row[3])
    return {
        "id": row[0],
        "sessionId": row[1],
        "rawQuery": row[2],
        "structure": structure,
        "selectedPlatforms": _loads(row[4]) or [],
        "searchTerms": _loads(row[5]) or {},
        "platformStatus": _loads(row[6]) if row[6] else None,
        "status": row[7],
        "createdAt": int(row[8].timestamp() * 1000) if row[8] else 0,
        "updatedAt": int(row[9].timestamp() * 1000) if row[9] else 0,
    }


def _require_db_user_id(user_id: str) -> int:
    db_user_id = _external_id_to_db_id(user_id)
    if db_user_id is None:
        raise ValueError("invalid user_id")
    return db_user_id


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def _loads(value):
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)
