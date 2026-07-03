/**
 * 数据入口的运行时规整。
 *
 * 后端返回经 JSON.parse 后被直接 `as ComparisonTask` —— 类型只是"愿望",运行期无保障。
 * 一条 subtasks/items 缺失的脏 task 就会让 ComparisonTaskCard 解构崩溃(历史白屏根因)。
 * 在 api.ts 的出口统一过一遍这里,保证下游拿到的 subtasks/items 一定是数组,把"每个
 * 消费者都得记得 ?? []"的系统性风险收敛到一处。
 */
import { ComparisonTask, ComparisonSubtask } from "../types";

export function normalizeComparisonTask(raw: any): ComparisonTask {
  const subtasks = Array.isArray(raw?.subtasks)
    ? raw.subtasks.map(normalizeSubtask)
    : [];
  return {
    id: String(raw?.id ?? ""),
    draftId: String(raw?.draftId ?? ""),
    status: raw?.status ?? "queued",
    createdAt: Number(raw?.createdAt ?? 0),
    completedAt: raw?.completedAt ?? null,
    subtasks,
  };
}

function normalizeSubtask(raw: any): ComparisonSubtask {
  return {
    ...raw,
    id: String(raw?.id ?? ""),
    platform: raw?.platform,
    status: raw?.status ?? "queued",
    searchTerms: Array.isArray(raw?.searchTerms) ? raw.searchTerms : [],
    items: Array.isArray(raw?.items) ? raw.items : [],
    error: raw?.error ?? null,
    createdAt: Number(raw?.createdAt ?? 0),
    updatedAt: Number(raw?.updatedAt ?? 0),
  };
}
