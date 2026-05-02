import { ChatMessage, ChatSession } from "../types";
import { authHeader } from "./auth";

const API_BASE = "/api";

export interface SessionSummary {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
}

export interface SessionDetail extends SessionSummary {
  messages: ChatMessage[];
}

async function handle401(res: Response) {
  if (res.status === 401) {
    window.dispatchEvent(new Event("mro:unauthorized"));
    throw new Error("登录已失效");
  }
}

export async function listSessions(): Promise<SessionSummary[]> {
  const res = await fetch(`${API_BASE}/chat/sessions`, { headers: authHeader() });
  await handle401(res);
  if (!res.ok) throw new Error(`获取会话列表失败: ${res.status}`);
  const data = await res.json();
  return data.sessions || [];
}

export async function getSession(id: string): Promise<SessionDetail | null> {
  const res = await fetch(`${API_BASE}/chat/sessions/${id}`, { headers: authHeader() });
  await handle401(res);
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`获取会话失败: ${res.status}`);
  return res.json();
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/sessions/${id}`, {
    method: "DELETE",
    headers: authHeader(),
  });
  await handle401(res);
  if (!res.ok && res.status !== 404) throw new Error(`删除失败: ${res.status}`);
}

export async function updateSessionTitle(id: string, title: string): Promise<void> {
  const res = await fetch(`${API_BASE}/chat/sessions/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeader() },
    body: JSON.stringify({ title }),
  });
  await handle401(res);
  if (!res.ok) throw new Error(`重命名失败: ${res.status}`);
}

export function summaryToSession(s: SessionSummary): ChatSession {
  return { ...s, messages: [] };
}

export function detailToSession(d: SessionDetail): ChatSession {
  return {
    id: d.id,
    title: d.title,
    createdAt: d.createdAt,
    messages: d.messages.map(m => ({
      ...m,
      isStreaming: false,
      slotClarification: (m as any).slotClarification,
    })),
  };
}
