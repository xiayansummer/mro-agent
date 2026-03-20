import { SkuItem } from "../types";

export async function submitFeedback(
  sessionId: string,
  action: "liked" | "disliked",
  sku: SkuItem,
): Promise<void> {
  try {
    await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        action,
        item_code: sku.item_code,
        item_name: sku.item_name,
        brand_name: sku.brand_name ?? "",
        l2_category: sku.l2_category_name ?? "",
        l3_category: sku.l3_category_name ?? "",
        specification: sku.specification ?? "",
      }),
    });
  } catch {
    // fire-and-forget, silent fail
  }
}

const API_BASE = "/api";

export interface SSECallbacks {
  onText: (text: string) => void;
  onSkuResults: (results: SkuItem[]) => void;
  onThinking: (msg: string) => void;
  onDone: () => void;
  onError: (err: string) => void;
}

export async function sendMessage(
  sessionId: string,
  message: string,
  callbacks: SSECallbacks,
  signal?: AbortSignal,
  imageBase64?: string,
): Promise<void> {
  const body: Record<string, string> = { session_id: sessionId, message };
  if (imageBase64) body.image_base64 = imageBase64;

  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    callbacks.onError(`请求失败: ${response.status}`);
    return;
  }

  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError("无法读取响应流");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let finished = false;
  let eventType = "";  // persists across chunks so event+data split across reads still works

  function handleEvent(event: string, data: string) {
    switch (event) {
      case "text":
        try {
          callbacks.onText(JSON.parse(data));
        } catch {
          callbacks.onText(data);
        }
        break;
      case "sku_results":
        try {
          callbacks.onSkuResults(JSON.parse(data));
        } catch (e) {
          console.error("Failed to parse SKU results:", e);
        }
        break;
      case "thinking":
        callbacks.onThinking(data);
        break;
      case "done":
        finished = true;
        callbacks.onDone();
        break;
      case "error":
        callbacks.onError(data);
        break;
    }
  }

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      if (!finished) callbacks.onDone();
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (line.startsWith("event: ")) {
        eventType = line.slice(7).trim();
      } else if (line.startsWith("data: ")) {
        const data = line.slice(6);
        handleEvent(eventType, data);
        eventType = "";
      }
    }
  }
}
