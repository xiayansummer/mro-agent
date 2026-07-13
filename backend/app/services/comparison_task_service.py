import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import text

from app.db.mysql import AsyncSessionLocal
from app.models.comparison import (
    ComparisonDraftStatus,
    ComparisonSubtaskStatus,
    ComparisonTaskStatus,
    ExtensionStatus,
)
from app.services import ehsy_comparison_source, extension_service
from app.services.comparison_ranker import rank_external_offers
from app.services.memory_service import memory_service
from app.services.user_service import _external_id_to_db_id, db_id_to_external_id  # noqa: F401
# 共享 helper(含时区安全的 _millis);re-export 保持 `from ...comparison_task_service
# import _millis`(test_audit_fixes 等)仍可用。
from app import platforms
from app.services.comparison_common import (  # noqa: F401
    _require_db_user_id,
    _new_id,
    _json,
    _loads,
    _millis,
)
# 状态机已拆到 comparison_task_status;re-export 使内部调用与外部 import 均不变。
from app.services.comparison_task_status import (  # noqa: F401
    _task_status_for_subtasks,
    _row_to_subtask,
    _refresh_task_status,
)
# 扩展队列 broker 已拆到 comparison_lease_broker;re-export 保持外部
# `comparison_task_service.lease_next_subtask/update_subtask_status/submit_subtask_results`
# 与 `_required_brand_from_structure`(test)、`SUBTASK_LEASE_SECONDS` 仍可用。
from app.services.comparison_lease_broker import (  # noqa: F401
    SUBTASK_LEASE_SECONDS,
    lease_next_subtask,
    update_subtask_status,
    submit_subtask_results,
    _required_brand_from_structure,
)

logger = logging.getLogger(__name__)


async def start_draft(draft_id: str, user_id: str) -> Optional[dict]:
    db_user_id = _require_db_user_id(user_id)

    async with AsyncSessionLocal() as session:
        draft_result = await session.execute(
            text(
                """
                SELECT id, selected_platforms, search_terms_json, structure_json
                FROM comparison_drafts
                WHERE id = :draft_id AND user_id = :uid
                """
            ),
            {"draft_id": draft_id, "uid": db_user_id},
        )
        draft = draft_result.fetchone()
        if not draft:
            return None

        # 防重复:同一草稿已建过 task 则复用最新,避免双击 / 重试建出多套子任务,
        # 进而让京东工业品 / 震坤行被重复抓取(浪费配额、触发风控)。
        existing = await session.execute(
            text(
                """
                SELECT id FROM comparison_tasks
                WHERE draft_id = :draft_id AND user_id = :uid
                ORDER BY created_at DESC
                LIMIT 1
                """
            ),
            {"draft_id": draft_id, "uid": db_user_id},
        )
        existing_row = existing.fetchone()
        if existing_row:
            return await get_task(existing_row[0], user_id)

        task_id = _new_id("cmp_task")
        selected_platforms = _loads(draft[1]) or list(platforms.DEFAULT_PLATFORMS)
        search_terms = _loads(draft[2]) or {}
        extension_status = await extension_service.get_extension_status(user_id)
        _ext_ids = platforms.extension_platform_ids()
        extension_platforms = [p for p in selected_platforms if p in _ext_ids]
        subtask_specs = _build_subtask_specs(extension_platforms, search_terms, extension_status)
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

    if "ehsy" in selected_platforms:
        _terms = search_terms if isinstance(search_terms, dict) else {}
        ehsy_terms = _terms.get("ehsy") or next((v for v in _terms.values() if v), [])
        await _inject_ehsy_subtask(task_id, user_id, _loads(draft[3]) or {}, ehsy_terms)

    return await get_task(task_id, user_id)


async def _inject_ehsy_subtask(task_id: str, user_id: str, structure: dict, terms: list) -> None:
    """后端服务端抓西域,排序后以 DONE 子任务落库。独立 session + try/except:
    西域故障绝不影响已提交的 jd/zkh 子任务。"""
    try:
        term = terms[0] if terms else ((structure or {}).get("specification") or {}).get("productType") or ""
        if not term:
            return
        raw = await ehsy_comparison_source.fetch_ehsy_offers(term)
        if not raw:
            # 也写一个 0 条的 DONE 子任务,让前端显示"西域:暂无匹配"
            raw_ranked = []
        else:
            preferences = await memory_service.get_preference_signals(user_id)
            raw_ranked = [
                {**o, "selectedSearchTerm": term}
                for o in rank_external_offers(structure, raw, preferences=preferences)
            ]
        subtask_id = _new_id("cmp_subtask")
        async with AsyncSessionLocal() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO comparison_subtasks (id, task_id, platform, status, search_terms_json, items_json)
                    VALUES (:id, :task_id, :platform, :status, :search_terms_json, :items_json)
                    """
                ),
                {
                    "id": subtask_id,
                    "task_id": task_id,
                    "platform": "ehsy",
                    "status": ComparisonSubtaskStatus.DONE.value,
                    "search_terms_json": _json([term]),
                    "items_json": _json(raw_ranked),
                },
            )
            await _refresh_task_status(session, subtask_id)
            await session.commit()
    except Exception:
        logger.warning("ehsy injection failed; comparison continues without 西域", exc_info=True)


def filter_disliked_items(subtasks: list[dict], disliked_skus) -> list[dict]:
    """读取路径的 disliked 过滤(纯函数,可单测)。

    写入路径(rank_external_offers)只管"新比价";已落库的 items_json 在轮询 /
    历史会话回放时由 get_task 原样返回——若不在这里过滤,用户标记"不合适"后
    一刷新/回看历史,该 offer 又复现。匹配口径与 ranker 一致:platformSku 或 id。
    """
    disliked = {str(s).strip() for s in (disliked_skus or []) if s}
    if not disliked:
        return subtasks
    filtered = []
    for subtask in subtasks:
        items = subtask.get("items") or []
        kept = [
            item
            for item in items
            if str(item.get("platformSku") or "").strip() not in disliked
            and str(item.get("id") or "").strip() not in disliked
        ]
        filtered.append({**subtask, "items": kept})
    return filtered


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

        if await _requeue_resolved_login_required_subtasks(session, task_id, db_user_id, user_id):
            await session.commit()
            task = (
                task[0],
                task[1],
                ComparisonTaskStatus.QUEUED.value,
                task[3],
                None,
            )

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

    # 读取路径同样剔除用户标记"不合适"的 offer(带 60s 进程内缓存,轮询不打爆 Memos)。
    disliked = await memory_service.get_disliked_skus_cached(user_id)
    subtasks = filter_disliked_items(subtasks, disliked)

    return {
        "id": task[0],
        "draftId": task[1],
        "status": task[2],
        "createdAt": _millis(task[3]),
        "completedAt": _millis(task[4]) if task[4] else None,
        "subtasks": subtasks,
    }


async def get_latest_task_for_draft(draft_id: str, user_id: str) -> Optional[dict]:
    db_user_id = _require_db_user_id(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT id
                FROM comparison_tasks
                WHERE draft_id = :draft_id AND user_id = :uid
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ),
            {"draft_id": draft_id, "uid": db_user_id},
        )
        row = result.fetchone()
    if not row:
        return None
    return await get_task(row[0], user_id)


async def get_latest_session_offers(session_id: str, user_id: str) -> Optional[list[dict]]:
    """本会话最近一个【有 offer】的比价 task 的全部 offers(跨平台拍平),无则 None。

    取的是"最近一个非空 task",而非"最近一个 task":比价可能被重跑/失败,最新的 task
    可能 0 offer(jd 重跑返空、zkh 未登录),而用户要精炼的是他们看到的、最近一次真出了
    结果的那批 offer——往往在更早的 task 里。只看最新一个 task 会把这些会话误报"无可精炼
    结果"。这里从最近若干个 task 新→旧扫,返回第一个有 offer 的;全空才 None。

    精炼指令的操作对象:不重新抓取,直接复用已采集结果(含 disliked 过滤,在 get_task 内)。
    """
    db_user_id = _require_db_user_id(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                SELECT t.id FROM comparison_tasks t
                JOIN comparison_drafts d ON t.draft_id = d.id
                WHERE d.chat_session_id = :sid AND t.user_id = :uid
                ORDER BY t.created_at DESC, t.id DESC
                LIMIT 10
                """
            ),
            {"sid": session_id, "uid": db_user_id},
        )
        rows = result.fetchall()
    for row in rows:
        task = await get_task(row[0], user_id)
        if not task:
            continue
        offers = [item for st in task.get("subtasks", []) for item in (st.get("items") or [])]
        if offers:
            return offers
    return None


async def retry_subtask(task_id: str, platform: str, user_id: str) -> Optional[dict]:
    db_user_id = _require_db_user_id(user_id)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            text(
                """
                UPDATE comparison_subtasks st
                JOIN comparison_tasks t ON t.id = st.task_id
                SET st.status = :queued,
                    st.items_json = NULL,
                    st.error_json = NULL,
                    st.leased_until = NULL
                WHERE st.task_id = :task_id
                  AND st.platform = :platform
                  AND t.user_id = :uid
                  AND st.status IN (:login_required, :failed, :timeout)
                """
            ),
            {
                "queued": ComparisonSubtaskStatus.QUEUED.value,
                "task_id": task_id,
                "platform": platform,
                "uid": db_user_id,
                "login_required": ComparisonSubtaskStatus.LOGIN_REQUIRED.value,
                "failed": ComparisonSubtaskStatus.FAILED.value,
                "timeout": ComparisonSubtaskStatus.TIMEOUT.value,
            },
        )
        if result.rowcount <= 0:
            await session.rollback()
            return None
        await session.execute(
            text(
                """
                UPDATE comparison_tasks
                SET status = :status, completed_at = NULL
                WHERE id = :task_id AND user_id = :uid
                """
            ),
            {"status": ComparisonTaskStatus.QUEUED.value, "task_id": task_id, "uid": db_user_id},
        )
        await session.commit()
    return await get_task(task_id, user_id)


async def _requeue_resolved_login_required_subtasks(
    session,
    task_id: str,
    db_user_id: int,
    user_id: str,
) -> int:
    result = await session.execute(
        text(
            """
            SELECT st.id, st.platform, st.error_json
            FROM comparison_subtasks st
            JOIN comparison_tasks t ON t.id = st.task_id
            WHERE st.task_id = :task_id
              AND t.user_id = :uid
              AND st.status = :login_required
            """
        ),
        {
            "task_id": task_id,
            "uid": db_user_id,
            "login_required": ComparisonSubtaskStatus.LOGIN_REQUIRED.value,
        },
    )
    blocked_subtasks = [
        (subtask_id, platform, error_json)
        for subtask_id, platform, error_json in result.fetchall()
        if _is_heartbeat_login_error(error_json)
    ]
    if not blocked_subtasks:
        return 0

    extension_status = await extension_service.get_extension_status(user_id)
    if not extension_status.online:
        return 0

    logged_in_platforms = {
        item.platform
        for item in extension_status.platforms
        if item.loggedIn is True or (item.platform == "zkh" and item.loggedIn is None)
    }
    if not logged_in_platforms:
        return 0

    changed = 0
    for subtask_id, platform, _error_json in blocked_subtasks:
        if platform not in logged_in_platforms:
            continue
        update_result = await session.execute(
            text(
                """
                UPDATE comparison_subtasks
                SET status = :queued,
                    items_json = NULL,
                    error_json = NULL,
                    leased_until = NULL
                WHERE id = :subtask_id
                """
            ),
            {
                "queued": ComparisonSubtaskStatus.QUEUED.value,
                "subtask_id": subtask_id,
            },
        )
        changed += max(update_result.rowcount, 0)

    if changed:
        await session.execute(
            text(
                """
                UPDATE comparison_tasks
                SET status = :status, completed_at = NULL
                WHERE id = :task_id AND user_id = :uid
                """
            ),
            {"status": ComparisonTaskStatus.QUEUED.value, "task_id": task_id, "uid": db_user_id},
        )
    return changed


def _is_heartbeat_login_error(raw_error: str | None) -> bool:
    error = _loads(raw_error) if raw_error else {}
    message = f"{error.get('code', '')} {error.get('message', '')}" if isinstance(error, dict) else str(raw_error or "")
    return any(
        marker in message
        for marker in (
            "login_required",
            "extension_offline",
            "平台未登录",
            "登录态未知",
            "Chrome 扩展未在线",
        )
    )


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


# _task_status_for_subtasks / _row_to_subtask / _refresh_task_status 已抽到
# comparison_task_status;_require_db_user_id / _new_id / _json / _loads / _millis 已抽到
# comparison_common。均见文件顶部的 re-export import。
