import { reportStatus } from "./api.js";
import { getSettings } from "./config.js";
import { collectLoginStatus } from "./loginProbe.js";

export async function collectPlatformStatus(force = false) {
  try {
    return await collectLoginStatus(force);
  } catch (error) {
    const checkedAt = new Date().toISOString();
    return [
      { platform: "jd", checkedAt, message: `登录态未知：${error.message || "探测失败"}` },
      { platform: "zkh", checkedAt, message: `登录态未知：${error.message || "探测失败"}` },
    ];
  }
}

let heartbeatInFlight = false;

// force=true:绕过登录态探测的 TTL 缓存、强制即时探测一次(手动「立即上报状态」用)。
// force=false(默认,定时心跳):走 TTL 缓存,避免每分钟真打开平台页触发风控。
export async function sendHeartbeat(force = false) {
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
      platforms: await collectPlatformStatus(force),
    });

    const lastHeartbeatAt = new Date().toISOString();
    await chrome.storage.local.set({ lastHeartbeatAt });
    return { skipped: false, lastHeartbeatAt };
  } finally {
    heartbeatInFlight = false;
  }
}
