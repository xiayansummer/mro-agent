"""比价链路共享的小工具:DB user id 解析、ID 生成、JSON 序列化、时区安全的毫秒时间戳。

原先 comparison_draft_service 与 comparison_task_service 各自复制了一份完全相同的
`_require_db_user_id` / `_new_id` / `_json` / `_loads` / `_millis`,且 draft_service 的
时间戳用裸 `.timestamp()`(非 UTC 容器上会偏整数小时,与 task 的 `_millis` 口径不一致)。
统一收敛到这里,所有 datetime→epoch 一律走时区安全的 `_millis`。
"""
import json
import uuid
from datetime import timezone

from app.services.user_service import _external_id_to_db_id


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
