/**
 * 比价任务轮询 —— InquiryPage(批量)与 ChatWindow(聊天)共用的一份实现。
 *
 * 原先两处各复制了一套带并发/去重/竞态规避的 setInterval 状态机(且已在细节上分叉),
 * 还都缺"终止上限 / 退避 / 可见性暂停",导致死任务(404/过期)永久每 2.5s 空转、
 * 批量场景放大成请求风暴。收敛到这一个 hook,并补齐:
 * - 连续失败达上限即停轮询该任务(不再对死任务永久重试)
 * - 后台标签页(document.hidden)暂停轮询
 * - 活跃集合变化时立即拉一次(切回视图不必干等一个 tick)
 */
import { useEffect, useRef } from "react";
import { ComparisonTask } from "../types";
import { getComparisonTask } from "../services/api";

export const POLL_INTERVAL_MS = 2500;
export const MAX_CONSECUTIVE_FAILURES = 5;

const ACTIVE_STATUSES = ["queued", "running", "partial"];

export interface PollTarget {
  /** 消费者自己的定位键:InquiryPage 用 row.index,ChatWindow 用 message id */
  key: string | number;
  taskId: string;
  /** 当前 task 状态;终态(done/failed/cancelled)不再轮询 */
  status?: string;
}

/** 纯函数:挑出仍需轮询的目标(非终态 + 未超连续失败上限)。可脱离 React 单测。 */
export function selectPollable(
  targets: PollTarget[],
  failures: Record<string, number>,
): PollTarget[] {
  return targets.filter(
    (t) =>
      !!t.taskId &&
      (!t.status || ACTIVE_STATUSES.includes(t.status)) &&
      (failures[t.taskId] ?? 0) < MAX_CONSECUTIVE_FAILURES,
  );
}

export function useComparisonPolling(
  targets: PollTarget[],
  onResult: (key: string | number, task: ComparisonTask) => void,
): void {
  const targetsRef = useRef(targets);
  targetsRef.current = targets;
  const onResultRef = useRef(onResult);
  onResultRef.current = onResult;
  const failuresRef = useRef<Record<string, number>>({});

  // 仅当"可轮询集合"变化时重建定时器,避免每次流式 render 都重建(与原实现同思路)
  const activeKey = selectPollable(targets, failuresRef.current)
    .map((t) => `${t.key}:${t.taskId}:${t.status ?? "new"}`)
    .join("|");

  useEffect(() => {
    if (selectPollable(targetsRef.current, failuresRef.current).length === 0) return;
    let cancelled = false;

    const tick = async () => {
      if (typeof document !== "undefined" && document.hidden) return;
      const batch = selectPollable(targetsRef.current, failuresRef.current);
      const results = await Promise.allSettled(batch.map((t) => getComparisonTask(t.taskId)));
      if (cancelled) return;
      batch.forEach((t, i) => {
        const r = results[i];
        if (r.status === "fulfilled") {
          failuresRef.current[t.taskId] = 0;
          onResultRef.current(t.key, r.value);
        } else {
          failuresRef.current[t.taskId] = (failuresRef.current[t.taskId] ?? 0) + 1;
        }
      });
    };

    const id = setInterval(tick, POLL_INTERVAL_MS);
    tick(); // 立即拉一次
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [activeKey]);
}
