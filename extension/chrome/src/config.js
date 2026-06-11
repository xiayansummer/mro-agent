export const DEFAULT_API_BASE = "https://mro.fultek.ai/api";
export const EXTENSION_VERSION = "0.2.1";
export const HEARTBEAT_ALARM = "mro-extension-heartbeat";
export const HEARTBEAT_PERIOD_MINUTES = 1;
// 登录态探测最小间隔:心跳每分钟一次,但"探测登录态"要真打开京东/震坤行页面,
// 每分钟都开会被平台风控判为爬虫、导致正经检索也被拦。探测加此 TTL 后,每个平台
// 最多每 30 分钟才真打开一次平台页;TTL 内的心跳复用缓存、不开页。详见 loginProbe.js。
export const LOGIN_PROBE_TTL_MINUTES = 30;

export async function getSettings() {
  const stored = await chrome.storage.local.get([
    "extToken",
    "sessionId",
    "deviceName",
    "lastHeartbeatAt",
    "pendingJdVerification",
  ]);
  return {
    apiBase: DEFAULT_API_BASE,
    extToken: stored.extToken || "",
    sessionId: stored.sessionId || "",
    deviceName: stored.deviceName || defaultDeviceName(),
    lastHeartbeatAt: stored.lastHeartbeatAt || "",
    pendingJdVerification: stored.pendingJdVerification || null,
  };
}

export function defaultDeviceName() {
  return `Chrome ${navigator.platform || "Device"}`;
}
