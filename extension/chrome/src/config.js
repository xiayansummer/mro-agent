export const DEFAULT_API_BASE = "https://mro.fultek.ai/api";
export const EXTENSION_VERSION = "0.1.0";
export const HEARTBEAT_ALARM = "mro-extension-heartbeat";
export const HEARTBEAT_PERIOD_MINUTES = 1;

export async function getSettings() {
  const stored = await chrome.storage.local.get([
    "extToken",
    "sessionId",
    "deviceName",
    "lastHeartbeatAt",
  ]);
  return {
    apiBase: DEFAULT_API_BASE,
    extToken: stored.extToken || "",
    sessionId: stored.sessionId || "",
    deviceName: stored.deviceName || defaultDeviceName(),
    lastHeartbeatAt: stored.lastHeartbeatAt || "",
  };
}

export function defaultDeviceName() {
  return `Chrome ${navigator.platform || "Device"}`;
}
