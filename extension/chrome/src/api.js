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
    return detailToString(body.detail ?? body.message);
  } catch {
    return "";
  }
}

// FastAPI 校验错误(422)的 detail 是对象数组 [{loc,msg,type},...],直接 String() 会得到
// "[object Object]" 掩盖真实原因。这里统一归一为可读字符串:字符串原样返回、数组取各项 msg
// 拼接、对象取 msg,兜底 JSON 序列化。任何 4xx/5xx 都能显示出人能看懂的错误。
export function detailToString(detail) {
  if (detail == null) return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((e) => (e && typeof e === "object" ? e.msg || JSON.stringify(e) : String(e)))
      .filter(Boolean)
      .join("；");
  }
  if (typeof detail === "object") return detail.msg || JSON.stringify(detail);
  return String(detail);
}
