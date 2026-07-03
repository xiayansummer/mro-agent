import { describe, it, expect } from "vitest";
import { createSSEParser, SSEEvent } from "./sseParser";

function collect() {
  const events: SSEEvent[] = [];
  const parser = createSSEParser((e) => events.push(e));
  return { events, parser };
}

describe("createSSEParser", () => {
  it("解析单个完整事件", () => {
    const { events, parser } = collect();
    parser.push("event: text\ndata: hello\n");
    expect(events).toEqual([{ event: "text", data: "hello" }]);
  });

  it("一个事件被拆成两个 network chunk 仍能正确组装", () => {
    const { events, parser } = collect();
    parser.push("event: comp");
    parser.push("arison_draft\ndata: {\"id\":1}\n");
    expect(events).toEqual([{ event: "comparison_draft", data: '{"id":1}' }]);
  });

  it("data 跨 chunk 拼接", () => {
    const { events, parser } = collect();
    parser.push("event: text\ndata: hel");
    parser.push("lo world\n");
    expect(events).toEqual([{ event: "text", data: "hello world" }]);
  });

  it("一次 push 含多个事件", () => {
    const { events, parser } = collect();
    parser.push("event: thinking\ndata: a\nevent: text\ndata: b\n");
    expect(events).toEqual([
      { event: "thinking", data: "a" },
      { event: "text", data: "b" },
    ]);
  });

  it("eventType 触发后重置(裸 data 行 event 为空)", () => {
    const { events, parser } = collect();
    parser.push("event: done\ndata: x\ndata: y\n");
    expect(events[0]).toEqual({ event: "done", data: "x" });
    expect(events[1]).toEqual({ event: "", data: "y" });
  });

  it("flush 补发无结尾换行的残留 data 行", () => {
    const { events, parser } = collect();
    parser.push("event: text\ndata: tail");
    expect(events).toHaveLength(0); // 半行还在缓冲
    parser.flush();
    expect(events).toEqual([{ event: "text", data: "tail" }]);
  });
});
