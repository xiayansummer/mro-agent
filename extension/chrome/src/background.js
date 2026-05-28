import {
  HEARTBEAT_ALARM,
  HEARTBEAT_PERIOD_MINUTES,
} from "./config.js";
import { sendHeartbeat } from "./status.js";
import { openPlatformLogin } from "./loginProbe.js";

chrome.runtime.onInstalled.addListener(async () => {
  await ensureHeartbeatAlarm();
});

chrome.runtime.onStartup.addListener(async () => {
  await ensureHeartbeatAlarm();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== HEARTBEAT_ALARM) return;
  sendHeartbeat().catch((error) => {
    console.warn("MRO extension heartbeat failed:", error);
  });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "MRO_SEND_HEARTBEAT") {
    sendHeartbeat()
      .then((result) => sendResponse({ ok: true, result }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "MRO_OPEN_PLATFORM_LOGIN") {
    openPlatformLogin(message.platform)
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  return false;
});

async function ensureHeartbeatAlarm() {
  await chrome.alarms.create(HEARTBEAT_ALARM, {
    delayInMinutes: 1,
    periodInMinutes: HEARTBEAT_PERIOD_MINUTES,
  });
}
