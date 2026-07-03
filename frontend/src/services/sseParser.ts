/**
 * SSE 分帧状态机(纯函数,可脱离 React/网络单测)。
 *
 * 原先这套逻辑内联在 api.ts 的 sendMessage 闭包里,依赖 callbacks/eventType,
 * 无法独立测"一个事件被拆成两个 network chunk 仍能正确组装"。抽成纯状态机后:
 * 喂任意切分的字符串片段,产出 {event, data} 序列。
 */
export interface SSEEvent {
  event: string;
  data: string;
}

export function createSSEParser(onEvent: (e: SSEEvent) => void) {
  let buffer = "";
  let eventType = ""; // 跨 chunk 保留:event 行与 data 行可能落在不同 read 里

  return {
    /** 灌入一段(可能不完整的)文本;按行切分,行内 event:/data: 前缀触发事件。 */
    push(chunk: string): void {
      buffer += chunk;
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? ""; // 最后一段可能是半行,留到下次
      for (const line of lines) {
        if (line.startsWith("event: ")) {
          eventType = line.slice(7).trim();
        } else if (line.startsWith("data: ")) {
          onEvent({ event: eventType, data: line.slice(6) });
          eventType = "";
        }
      }
    },
    /** 流结束时冲刷:若缓冲里还残留一条完整的 data 行(无结尾换行),补发。 */
    flush(): void {
      if (buffer.startsWith("data: ")) {
        onEvent({ event: eventType, data: buffer.slice(6) });
      }
      buffer = "";
      eventType = "";
    },
  };
}
