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

let heartbeatInFlight = false;

export async function sendHeartbeat() {
  const settings = await getSettings();
  if (!settings.extToken) {
    return { skipped: true, reason: "not_bound" };
  }

  // 60s alarm 与手动触发可能重叠;并发执行会重复打开探测页且 last-write-wins。
  // 与 background.js 的 taskRunning 守卫对齐,飞行中直接跳过。
  if (heartbeatInFlight) return { skipped: true, reason: "in_flight" };
  heartbeatInFlight = true;
  try {
    await reportStatus(settings.apiBase, settings.extToken, {
      deviceName: settings.deviceName,
      platforms: await collectPlatformStatus(),
    });

    const lastHeartbeatAt = new Date().toISOString();
    await chrome.storage.local.set({ lastHeartbeatAt });
    return { skipped: false, lastHeartbeatAt };
  } finally {
    heartbeatInFlight = false;
  }
}
