import { reportStatus } from "./api.js";
import { getSettings } from "./config.js";
import { collectLoginStatus } from "./loginProbe.js";

export async function collectPlatformStatus() {
  try {
    return await collectLoginStatus();
  } catch (error) {
    const checkedAt = new Date().toISOString();
    return [
      { platform: "jd", checkedAt, message: `登录态未知：${error.message || "探测失败"}` },
      { platform: "zkh", checkedAt, message: `登录态未知：${error.message || "探测失败"}` },
    ];
  }
}

export async function sendHeartbeat() {
  const settings = await getSettings();
  if (!settings.extToken) {
    return { skipped: true, reason: "not_bound" };
  }

  await reportStatus(settings.apiBase, settings.extToken, {
    deviceName: settings.deviceName,
    platforms: await collectPlatformStatus(),
  });

  const lastHeartbeatAt = new Date().toISOString();
  await chrome.storage.local.set({ lastHeartbeatAt });
  return { skipped: false, lastHeartbeatAt };
}
