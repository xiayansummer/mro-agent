import { AuthUser } from "../types";

const API_BASE = "/api";
const STORAGE_KEY = "mro-auth-user";

export function getStoredUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: AuthUser | null) {
  if (user) localStorage.setItem(STORAGE_KEY, JSON.stringify(user));
  else localStorage.removeItem(STORAGE_KEY);
}

export function authHeader(): Record<string, string> {
  const user = getStoredUser();
  return user ? { Authorization: `Bearer ${user.auth_token}` } : {};
}

async function parseError(res: Response): Promise<string> {
  try {
    const data = await res.json();
    return data.detail || `请求失败 (${res.status})`;
  } catch {
    return `请求失败 (${res.status})`;
  }
}

export async function register(
  phone: string,
  nickname: string | null,
  inviteToken: string,
): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone, nickname, invite_token: inviteToken }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const user = (await res.json()) as AuthUser;
  setStoredUser(user);
  return user;
}

export async function login(phone: string): Promise<AuthUser> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phone }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  const user = (await res.json()) as AuthUser;
  setStoredUser(user);
  return user;
}

export async function fetchMe(): Promise<AuthUser | null> {
  const stored = getStoredUser();
  if (!stored) return null;
  const res = await fetch(`${API_BASE}/auth/me`, { headers: authHeader() });
  if (!res.ok) {
    setStoredUser(null);
    return null;
  }
  const user = (await res.json()) as AuthUser;
  setStoredUser(user);
  return user;
}

export function logout() {
  setStoredUser(null);
}
