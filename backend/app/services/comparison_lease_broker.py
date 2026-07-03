"""比价子任务的租约/队列 broker —— Chrome 扩展面向的取任务/回写接口。

从 comparison_task_service(原 773 行上帝模块)拆出的"扩展队列 broker"职责:
- lease_next_subtask: 乐观锁抢占一个 queued 子任务并加 90s 租约
- update_subtask_status / submit_subtask_results: 扩展回写状态/结果
与"建任务/读任务"的 CRUD、任务状态机分属不同数据流,拆开各自内聚。
状态推导统一走 comparison_task_status._refresh_task_status。
"""
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import text

from app.db.mysql import AsyncSessionLocal
from app.models.comparison import ComparisonSubtaskStatus, ComparisonTaskStatus
from app.services import extension_service
from app.services.comparison_common import _json, _loads, _millis
from app.services.comparison_ranker import rank_external_offers
from app.services.comparison_task_status import _refresh_task_status
from app.services.memory_service import memory_service
from app.services.user_service import db_id_to_external_id

SUBTASK_LEASE_SECONDS = 90


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
                SELECT st.id, st.task_id, st.platform, st.search_terms_json, d.structure_json
                FROM comparison_subtasks st
                JOIN comparison_tasks t ON t.id = st.task_id
                JOIN comparison_drafts d ON d.id = t.draft_id
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
        "requiredBrand": _required_brand_from_structure(candidate[4]),
        # 时区安全:leased_until 来自 datetime.utcnow()(naive UTC),走 _millis 声明 UTC
        "leasedUntil": _millis(leased_until),
    }


async def update_subtask_status(ext_token: str, subtask_id: str, status: str, message: Optional[str] = None) -> bool:
    extension_session = await extension_service.get_session_by_token(ext_token)
    if not extension_session or status not in {item.value for item in ComparisonSubtaskStatus}:
        return False

    error_json = _json({"message": message}) if message else None
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE comparison_subtasks st
                JOIN comparison_tasks t ON t.id = st.task_id
                SET st.status = :status,
                    st.error_json = :error_json,
                    st.leased_until = NULL
                WHERE st.id = :subtask_id AND t.user_id = :uid
                """
            ),
            {
                "status": status,
                "error_json": error_json,
                "subtask_id": subtask_id,
                "uid": extension_session["userId"],
            },
        )
        if result.rowcount <= 0:
            await session.rollback()
            return False
        await _refresh_task_status(session, subtask_id)
        await session.commit()
    return True


async def submit_subtask_results(
    ext_token: str,
    subtask_id: str,
    platform: str,
    search_term: str,
    offers: list[dict],
) -> bool:
    extension_session = await extension_service.get_session_by_token(ext_token)
    if not extension_session:
        return False

    async with AsyncSessionLocal() as session:
        structure = await _get_task_structure_for_subtask(session, subtask_id, extension_session["userId"])
        if structure is None:
            return False

        # 取用户历史偏好,传入 ranker 做 DPO 硬加权(命中偏好品牌/品类显著提分)。
        # get_preference_signals 内部已 try/except,失败返回空、不阻塞排序。
        preferences = await memory_service.get_preference_signals(
            db_id_to_external_id(extension_session["userId"])
        )

        items = [
            {
                **offer,
                "selectedSearchTerm": search_term,
            }
            for offer in rank_external_offers(structure, offers, preferences=preferences)
        ]
        result = await session.execute(
            text(
                """
                UPDATE comparison_subtasks st
                JOIN comparison_tasks t ON t.id = st.task_id
                SET st.status = :status,
                    st.items_json = :items_json,
                    st.error_json = NULL,
                    st.leased_until = NULL
                WHERE st.id = :subtask_id
                  AND st.platform = :platform
                AND t.user_id = :uid
                """
            ),
            {
                "status": ComparisonSubtaskStatus.DONE.value,
                "items_json": _json(items),
                "subtask_id": subtask_id,
                "platform": platform,
                "uid": extension_session["userId"],
            },
        )
        if result.rowcount <= 0:
            await session.rollback()
            return False
        await _refresh_task_status(session, subtask_id)
        await session.commit()
    return True


async def _get_task_structure_for_subtask(session, subtask_id: str, user_id: int) -> Optional[dict]:
    result = await session.execute(
        text(
            """
            SELECT d.structure_json
            FROM comparison_subtasks st
            JOIN comparison_tasks t ON t.id = st.task_id
            JOIN comparison_drafts d ON d.id = t.draft_id
            WHERE st.id = :subtask_id AND t.user_id = :uid
            """
        ),
        {"subtask_id": subtask_id, "uid": user_id},
    )
    row = result.fetchone()
    if not row:
        return None
    return _loads(row[0]) or {}


def _required_brand_from_structure(raw_structure: str | None) -> str:
    structure = _loads(raw_structure) if raw_structure else {}
    brand = structure.get("specification", {}).get("brand") if isinstance(structure, dict) else None
    return str(brand or "").strip()
