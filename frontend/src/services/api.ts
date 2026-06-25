import {
  SkuItem,
  CompetitorItem,
  ExternalOffer,
  SlotClarification,
  ComparisonDraft,
  ComparisonTask,
  ChatMessage,
  ExtensionPairingCode,
  ExtensionStatus,
} from "../types";
import { authHeader } from "./auth";

export async function submitFeedback(
  sessionId: string,
  action: "liked" | "disliked",
  sku: SkuItem,
): Promise<void> {
  try {
    await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
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

export async function submitExternalOfferFeedback(
  sessionId: string,
  action: "liked" | "disliked",
  offer: ExternalOffer,
): Promise<boolean> {
  // 返回成败:调用方据此决定乐观移除是否回滚。若静默吞错,
  // "不合适"看着移除了但 Memos 没记录,下次比价又复现。
  try {
    const response = await fetch(`${API_BASE}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeader() },
      body: JSON.stringify({
        session_id: sessionId,
        action,
        item_code: offer.platformSku || offer.id,
        item_name: offer.title,
        brand_name: offer.brand ?? "",
        l2_category: offer.platform,
        l3_category: "外部平台候选",
        specification: offer.specText ?? "",
      }),
    });
    return response.ok;
  } catch {
    return false;
  }
}

const API_BASE = "/api";

export interface SSECallbacks {
  onText: (text: string) => void;
  onSkuResults: (results: SkuItem[]) => void;
  onCompetitorResults: (results: CompetitorItem[]) => void;
  onSlotClarification?: (slot: SlotClarification) => void;
  onComparisonDraft?: (draft: ComparisonDraft) => void;
  onRefinedOffers?: (r: NonNullable<ChatMessage["refinedOffers"]>) => void;
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
  skipClarification?: boolean,
): Promise<void> {
  const body: Record<string, unknown> = { session_id: sessionId, message };
  if (imageBase64) body.image_base64 = imageBase64;
  if (skipClarification) body.skip_clarification = true;

  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(body),
    signal,
  });

  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new Event("mro:unauthorized"));
      callbacks.onError("登录已失效，请重新登录");
      return;
    }
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
      case "competitor_results":
        try {
          callbacks.onCompetitorResults(JSON.parse(data));
        } catch (e) {
          console.error("Failed to parse competitor results:", e);
        }
        break;
      case "slot_clarification":
        try {
          callbacks.onSlotClarification?.(JSON.parse(data));
        } catch (e) {
          console.error("Failed to parse slot_clarification:", e);
        }
        break;
      case "comparison_draft":
        try {
          callbacks.onComparisonDraft?.(JSON.parse(data));
        } catch (e) {
          console.error("Failed to parse comparison_draft:", e);
        }
        break;
      case "refined_offers":
        try { callbacks.onRefinedOffers?.(JSON.parse(data)); } catch (e) { console.error("refined_offers parse", e); }
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

export async function startComparisonDraft(draftId: string): Promise<ComparisonTask> {
  const response = await fetch(`${API_BASE}/comparison/drafts/${draftId}/start`, {
    method: "POST",
    headers: authHeader(),
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error(await responseText(response, "启动比价失败"));
  }
  return response.json();
}

export async function getComparisonTask(taskId: string): Promise<ComparisonTask> {
  const response = await fetch(`${API_BASE}/comparison/tasks/${taskId}`, {
    headers: authHeader(),
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error(await responseText(response, "获取比价任务失败"));
  }
  return response.json();
}

export async function retryComparisonPlatform(
  taskId: string,
  platform: ComparisonTask["subtasks"][number]["platform"],
): Promise<ComparisonTask> {
  const response = await fetch(`${API_BASE}/comparison/tasks/${taskId}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ platform }),
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error(await responseText(response, "重试比价平台失败"));
  }
  return response.json();
}

export async function getExtensionStatus(): Promise<ExtensionStatus> {
  const response = await fetch(`${API_BASE}/extension/status`, {
    headers: authHeader(),
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error(await responseText(response, "获取扩展状态失败"));
  }
  return response.json();
}

export async function createExtensionPairingCode(): Promise<ExtensionPairingCode> {
  const response = await fetch(`${API_BASE}/extension/pairing-code`, {
    method: "POST",
    headers: authHeader(),
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error(await responseText(response, "生成扩展配对码失败"));
  }
  return response.json();
}

async function responseText(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return body.detail || body.message || fallback;
  } catch {
    return `${fallback}: ${response.status}`;
  }
}

export interface CompareRowResponse {
  ok: boolean;
  taskId?: string;
  draftId?: string;
  guidance?: string;
}

export async function compareInquiryRow(row: {
  需求品名?: string;
  需求品牌?: string;
  需求型号?: string;
}): Promise<CompareRowResponse> {
  const response = await fetch(`${API_BASE}/inquiry/compare-row`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify(row),
  });
  if (!response.ok) {
    if (response.status === 401) window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error(await responseText(response, "外部比价启动失败"));
  }
  return response.json();
}
