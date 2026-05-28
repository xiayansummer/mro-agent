import { EXTENSION_VERSION } from "./config.js";

export async function registerExtension(apiBase, code, deviceName) {
  const response = await fetch(`${apiBase}/extension/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      code,
      deviceName,
      version: EXTENSION_VERSION,
    }),
  });
  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(detail || `绑定失败：${response.status}`);
  }
  return response.json();
}

export async function reportStatus(apiBase, extToken, payload) {
  const response = await fetch(`${apiBase}/extension/status`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Extension-Token": extToken,
    },
    body: JSON.stringify({
      deviceName: payload.deviceName,
      version: EXTENSION_VERSION,
      platforms: payload.platforms || [],
    }),
  });
  if (!response.ok) {
    const detail = await safeDetail(response);
    throw new Error(detail || `状态上报失败：${response.status}`);
  }
  return response.json();
}

async function safeDetail(response) {
  try {
    const body = await response.json();
    return body.detail || body.message || "";
  } catch {
    return "";
  }
}
