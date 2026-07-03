"""比价任务状态机:子任务集合 → task 状态推导,以及 DB row → subtask dict 的映射。

从 comparison_task_service(原 773 行上帝模块)拆出的"状态"职责。task 状态只此一处真源:
建任务(start_draft 用 _task_status_for_subtasks)与运行中回填(submit/update/retry 触发
_refresh_task_status)都走这里,避免同一状态两处各算一套。
"""
from datetime import datetime

from sqlalchemy import text

from app.models.comparison import ComparisonSubtaskStatus, ComparisonTaskStatus
from app.services.comparison_common import _loads, _millis


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
