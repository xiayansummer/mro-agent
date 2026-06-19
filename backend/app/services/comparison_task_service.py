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
from app.services.user_service import _external_id_to_db_id, db_id_to_external_id

logger = logging.getLogger(__name__)

SUBTASK_LEASE_SECONDS = 90


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
        selected_platforms = _loads(draft[1]) or ["jd", "zkh", "ehsy"]
        search_terms = _loads(draft[2]) or {}
        extension_status = await extension_service.get_extension_status(user_id)
        extension_platforms = [p for p in selected_platforms if p != "ehsy"]
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
        await _inject_ehsy_subtask(task_id, user_id, _loads(draft[3]) or {}, search_terms)

    return await get_task(task_id, user_id)


def _ehsy_search_term(search_terms: dict, structure: dict) -> str:
    for key in ("jd", "zkh"):
        terms = search_terms.get(key) or []
        if terms:
            return terms[0]
    return ((structure or {}).get("specification") or {}).get("productType") or ""


async def _inject_ehsy_subtask(task_id: str, user_id: str, structure: dict, search_terms: dict) -> None:
    """后端服务端抓西域,排序后以 DONE 子任务落库。独立 session + try/except:
    西域故障绝不影响已提交的 jd/zkh 子任务。"""
    try:
        term = _ehsy_search_term(search_terms, structure)
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
        "leasedUntil": int(leased_until.timestamp() * 1000),
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


def _required_brand_from_structure(raw_structure: str | None) -> str:
    structure = _loads(raw_structure) if raw_structure else {}
    brand = structure.get("specification", {}).get("brand") if isinstance(structure, dict) else None
    return str(brand or "").strip()


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


async def _refresh_task_status(session, subtask_id: str) -> None:
    task_result = await session.execute(
        text("SELECT task_id FROM comparison_subtasks WHERE id = :subtask_id"),
        {"subtask_id": subtask_id},
    )
    task = task_result.fetchone()
    if not task:
        return

    counts_result = await session.execute(
        text(
            """
            SELECT status, COUNT(*)
            FROM comparison_subtasks
            WHERE task_id = :task_id
            GROUP BY status
            """
        ),
        {"task_id": task[0]},
    )
    counts = {row[0]: int(row[1]) for row in counts_result.fetchall()}
    total = sum(counts.values())
    done = counts.get(ComparisonSubtaskStatus.DONE.value, 0)
    terminal = done + counts.get(ComparisonSubtaskStatus.FAILED.value, 0) + counts.get(
        ComparisonSubtaskStatus.TIMEOUT.value, 0
    ) + counts.get(ComparisonSubtaskStatus.LOGIN_REQUIRED.value, 0)

    if total > 0 and done == total:
        task_status = ComparisonTaskStatus.DONE.value
        completed_at = datetime.utcnow()
    elif total > 0 and terminal == total:
        task_status = ComparisonTaskStatus.PARTIAL.value if done else ComparisonTaskStatus.FAILED.value
        completed_at = datetime.utcnow()
    elif counts.get(ComparisonSubtaskStatus.IN_PROGRESS.value, 0) > 0:
        task_status = ComparisonTaskStatus.RUNNING.value
        completed_at = None
    else:
        task_status = ComparisonTaskStatus.QUEUED.value
        completed_at = None

    await session.execute(
        text(
            """
            UPDATE comparison_tasks
            SET status = :status, completed_at = :completed_at
            WHERE id = :task_id
            """
        ),
        {"status": task_status, "completed_at": completed_at, "task_id": task[0]},
    )


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
    # DB 读出的是 naive datetime(代表 UTC 值)。裸 .timestamp() 会按运行机器本地
    # 时区解释,非 UTC 容器上会偏整数小时;显式声明为 UTC,与机器时区解耦。
    if not value:
        return 0
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.timestamp() * 1000)
