export const DEFAULT_API_BASE = "http://localhost:8000/api";
export const EXTENSION_VERSION = "0.1.0";
export const HEARTBEAT_ALARM = "mro-extension-heartbeat";
export const HEARTBEAT_PERIOD_MINUTES = 1;

export async function getSettings() {
  const stored = await chrome.storage.local.get([
    "apiBase",
    "extToken",
    "sessionId",
    "deviceName",
    "lastHeartbeatAt",
  ]);
  return {
    apiBase: stored.apiBase || DEFAULT_API_BASE,
    extToken: stored.extToken || "",
    sessionId: stored.sessionId || "",
    deviceName: stored.deviceName || defaultDeviceName(),
    lastHeartbeatAt: stored.lastHeartbeatAt || "",
  };
}

export function defaultDeviceName() {
  return `Chrome ${navigator.platform || "Device"}`;
}

export function normalizeApiBase(value) {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  if (!trimmed) return DEFAULT_API_BASE;
  return trimmed.endsWith("/api") ? trimmed : `${trimmed}/api`;
}
