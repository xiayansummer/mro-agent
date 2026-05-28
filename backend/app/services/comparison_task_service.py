import json
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.db.mysql import AsyncSessionLocal
from app.models.comparison import (
    ComparisonDraftStatus,
    ComparisonSubtaskStatus,
    ComparisonTaskStatus,
    ExtensionStatus,
)
from app.services import extension_service
from app.services.user_service import _external_id_to_db_id

SUBTASK_LEASE_SECONDS = 90


async def start_draft(draft_id: str, user_id: str) -> Optional[dict]:
    db_user_id = _require_db_user_id(user_id)
    task_id = _new_id("cmp_task")

    async with AsyncSessionLocal() as session:
        draft_result = await session.execute(
            text(
                """
                SELECT id, selected_platforms, search_terms_json
                FROM comparison_drafts
                WHERE id = :draft_id AND user_id = :uid
                """
            ),
            {"draft_id": draft_id, "uid": db_user_id},
        )
        draft = draft_result.fetchone()
        if not draft:
            return None

        selected_platforms = _loads(draft[1]) or ["jd", "zkh"]
        search_terms = _loads(draft[2]) or {}
        extension_status = await extension_service.get_extension_status(user_id)
        subtask_specs = _build_subtask_specs(selected_platforms, search_terms, extension_status)
        task_status = _task_status_for_subtasks(subtask_specs)
        draft_status = (
            ComparisonDraftStatus.TASK_CREATED
            if any(item["status"] == ComparisonSubtaskStatus.QUEUED.value for item in subtask_specs)
            else ComparisonDraftStatus.NEEDS_LOGIN
        )

        await session.execute(
            text(
                """
                INSERT INTO comparison_tasks (id, draft_id, user_id, status)
                VALUES (:id, :draft_id, :uid, :status)
                """
            ),
            {
                "id": task_id,
                "draft_id": draft_id,
                "uid": db_user_id,
                "status": task_status,
            },
        )
        for item in subtask_specs:
            await session.execute(
                text(
                    """
                    INSERT INTO comparison_subtasks (
                        id, task_id, platform, status, search_terms_json, error_json
                    ) VALUES (
                        :id, :task_id, :platform, :status, :search_terms_json, :error_json
                    )
                    """
                ),
                {
                    "id": _new_id("cmp_subtask"),
                    "task_id": task_id,
                    "platform": item["platform"],
                    "status": item["status"],
                    "search_terms_json": _json(item["searchTerms"]),
                    "error_json": _json(item["error"]) if item["error"] else None,
                },
            )
        await session.execute(
            text(
                """
                UPDATE comparison_drafts
                SET status = :status, platform_status_json = :platform_status
                WHERE id = :draft_id AND user_id = :uid
                """
            ),
            {
                "status": draft_status.value,
                "platform_status": _json(extension_status.model_dump(mode="json")),
                "draft_id": draft_id,
                "uid": db_user_id,
            },
        )
        await session.commit()

    return await get_task(task_id, user_id)


async def get_task(task_id: str, user_id: str) -> Optional[dict]:
    db_user_id = _require_db_user_id(user_id)
    async with AsyncSessionLocal() as session:
        task_result = await session.execute(
            text(
                """
                SELECT id, draft_id, status, created_at, completed_at
                FROM comparison_tasks
                WHERE id = :task_id AND user_id = :uid
                """
            ),
            {"task_id": task_id, "uid": db_user_id},
        )
        task = task_result.fetchone()
        if not task:
            return None

        subtasks_result = await session.execute(
            text(
                """
                SELECT id, platform, status, search_terms_json, items_json,
                       error_json, leased_until, created_at, updated_at
                FROM comparison_subtasks
                WHERE task_id = :task_id
                ORDER BY created_at, id
                """
            ),
            {"task_id": task_id},
        )
        subtasks = [_row_to_subtask(row) for row in subtasks_result.fetchall()]

    return {
        "id": task[0],
        "draftId": task[1],
        "status": task[2],
        "createdAt": _millis(task[3]),
        "completedAt": _millis(task[4]) if task[4] else None,
        "subtasks": subtasks,
    }


async def lease_next_subtask(ext_token: str) -> Optional[dict]:
    extension_session = await extension_service.get_session_by_token(ext_token)
    if not extension_session:
        return None

    now = datetime.utcnow()
    leased_until = now + timedelta(seconds=SUBTASK_LEASE_SECONDS)
    async with AsyncSessionLocal() as session:
        candidate_result = await session.execute(
            text(
                """
                SELECT st.id, st.task_id, st.platform, st.search_terms_json
                FROM comparison_subtasks st
                JOIN comparison_tasks t ON t.id = st.task_id
                WHERE t.user_id = :uid
                  AND st.status = :queued
                  AND (st.leased_until IS NULL OR st.leased_until < :now)
                ORDER BY st.created_at, st.id
                LIMIT 1
                """
            ),
            {
                "uid": extension_session["userId"],
                "queued": ComparisonSubtaskStatus.QUEUED.value,
                "now": now,
            },
        )
        candidate = candidate_result.fetchone()
        if not candidate:
            return None

        update_result = await session.execute(
            text(
                """
                UPDATE comparison_subtasks
                SET status = :status, leased_until = :leased_until
                WHERE id = :id
                  AND status = :queued
                  AND (leased_until IS NULL OR leased_until < :now)
                """
            ),
            {
                "status": ComparisonSubtaskStatus.IN_PROGRESS.value,
                "leased_until": leased_until,
                "id": candidate[0],
                "queued": ComparisonSubtaskStatus.QUEUED.value,
                "now": now,
            },
        )
        if update_result.rowcount <= 0:
            await session.rollback()
            return None
        await session.execute(
            text("UPDATE comparison_tasks SET status = :status WHERE id = :task_id"),
            {"status": ComparisonTaskStatus.RUNNING.value, "task_id": candidate[1]},
        )
        await session.commit()

    return {
        "subtaskId": candidate[0],
        "taskId": candidate[1],
        "platform": candidate[2],
        "searchTerms": _loads(candidate[3]) or [],
        "leasedUntil": int(leased_until.timestamp() * 1000),
    }


def _build_subtask_specs(
    selected_platforms: list[str],
    search_terms: dict,
    extension_status: ExtensionStatus,
) -> list[dict]:
    platform_status = {
        item.platform: item
        for item in extension_status.platforms
    }
    specs = []
    for platform in selected_platforms:
        status = platform_status.get(platform)
        terms = search_terms.get(platform) or []
        if not extension_status.online:
            specs.append(_blocked_subtask(platform, terms, "extension_offline", "Chrome 扩展未在线"))
        elif not status or status.loggedIn is not True:
            specs.append(_blocked_subtask(platform, terms, "login_required", "平台未登录或登录态未知"))
        else:
            specs.append({"platform": platform, "searchTerms": terms, "status": "queued", "error": None})
    return specs


def _blocked_subtask(platform: str, terms: list[str], code: str, message: str) -> dict:
    return {
        "platform": platform,
        "searchTerms": terms,
        "status": ComparisonSubtaskStatus.LOGIN_REQUIRED.value,
        "error": {"code": code, "message": message},
    }


def _task_status_for_subtasks(subtasks: list[dict]) -> str:
    if any(item["status"] == ComparisonSubtaskStatus.QUEUED.value for item in subtasks):
        return ComparisonTaskStatus.QUEUED.value
    return ComparisonTaskStatus.PARTIAL.value


def _row_to_subtask(row) -> dict:
    return {
        "id": row[0],
        "platform": row[1],
        "status": row[2],
        "searchTerms": _loads(row[3]) or [],
        "items": _loads(row[4]) or [],
        "error": _loads(row[5]) if row[5] else None,
        "leasedUntil": _millis(row[6]) if row[6] else None,
        "createdAt": _millis(row[7]),
        "updatedAt": _millis(row[8]),
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


def _millis(value) -> int:
    return int(value.timestamp() * 1000) if value else 0
