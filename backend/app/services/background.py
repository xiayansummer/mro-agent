"""Fire-and-forget 后台任务的共享工具。

原先 routers/chat.py、services/agent.py、services/memory_service.py 各复制了一份
相同的 `_background_tasks` set + ensure_future + add + add_done_callback(discard) 样板;
任一处漏掉 add_done_callback 都会让在途任务被 GC 中途回收。收敛到这里一处。
"""
import asyncio

# 持有强引用防止在途任务被 GC 回收;任务完成后自动丢弃引用。
_background_tasks: set = set()


def spawn_background(coro) -> asyncio.Task:
    task = asyncio.ensure_future(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
