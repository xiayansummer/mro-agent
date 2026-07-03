import { describe, it, expect } from "vitest";
import { selectPollable, MAX_CONSECUTIVE_FAILURES, PollTarget } from "./useComparisonPolling";

describe("selectPollable", () => {
  const t = (key: number, taskId: string, status?: string): PollTarget => ({ key, taskId, status });

  it("非终态任务需要轮询", () => {
    const targets = [t(1, "a", "queued"), t(2, "b", "running"), t(3, "c", "partial")];
    expect(selectPollable(targets, {}).map((x) => x.taskId)).toEqual(["a", "b", "c"]);
  });

  it("终态任务不轮询", () => {
    const targets = [t(1, "a", "done"), t(2, "b", "failed"), t(3, "c", "cancelled")];
    expect(selectPollable(targets, {})).toEqual([]);
  });

  it("无状态(刚创建、task 未回)也轮询", () => {
    expect(selectPollable([t(1, "a", undefined)], {})).toHaveLength(1);
  });

  it("空 taskId 跳过", () => {
    expect(selectPollable([t(1, "", "queued")], {})).toEqual([]);
  });

  it("连续失败达上限后停轮询该任务(防死任务永久空转)", () => {
    const targets = [t(1, "dead", "queued")];
    expect(selectPollable(targets, { dead: MAX_CONSECUTIVE_FAILURES - 1 })).toHaveLength(1);
    expect(selectPollable(targets, { dead: MAX_CONSECUTIVE_FAILURES })).toEqual([]);
  });
});
