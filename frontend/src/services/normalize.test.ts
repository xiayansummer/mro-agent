import { describe, it, expect } from "vitest";
import { normalizeComparisonTask } from "./normalize";

describe("normalizeComparisonTask", () => {
  it("保留合法 task 的字段与子任务", () => {
    const t = normalizeComparisonTask({
      id: "task-1",
      draftId: "draft-1",
      status: "running",
      createdAt: 123,
      subtasks: [
        { id: "s1", platform: "jd", status: "done", searchTerms: ["a"], items: [{ id: "o1" }] },
      ],
    });
    expect(t.id).toBe("task-1");
    expect(t.status).toBe("running");
    expect(t.subtasks).toHaveLength(1);
    expect(t.subtasks[0].items).toEqual([{ id: "o1" }]);
  });

  it("subtasks 缺失 → 空数组(白屏根因防护)", () => {
    const t = normalizeComparisonTask({ id: "x", status: "queued" });
    expect(t.subtasks).toEqual([]);
  });

  it("subtask.items 缺失/非数组 → 空数组", () => {
    const t = normalizeComparisonTask({
      subtasks: [{ id: "s1", platform: "jd", status: "queued" }, { id: "s2", items: "oops" }],
    });
    expect(t.subtasks[0].items).toEqual([]);
    expect(t.subtasks[1].items).toEqual([]);
  });

  it("null / 垃圾输入 → 安全默认,不抛异常", () => {
    expect(() => normalizeComparisonTask(null)).not.toThrow();
    expect(() => normalizeComparisonTask("garbage")).not.toThrow();
    const t = normalizeComparisonTask(null);
    expect(t.subtasks).toEqual([]);
    expect(t.id).toBe("");
  });

  it("含 1688 subtask 的 task 正常规整", () => {
    const t = normalizeComparisonTask({
      subtasks: [{ id: "s", platform: "1688", status: "done", items: [{ id: "o", platform: "1688" }] }],
    });
    expect(t.subtasks[0].platform).toBe("1688");
    expect(t.subtasks[0].items).toHaveLength(1);
  });
});
