import {
  HEARTBEAT_ALARM,
  HEARTBEAT_PERIOD_MINUTES,
  getSettings,
} from "./config.js";
import { sendHeartbeat } from "./status.js";
import { openPlatformLogin } from "./loginProbe.js";
import {
  fetchNextTask,
  submitSubtaskResults,
  updateSubtaskStatus,
} from "./taskApi.js";
import { runJdSearchTask } from "./jdSearch.js";
import { runZkhSearchTask } from "./zkhSearch.js";
import { decideSubtaskOutcome } from "./taskOutcome.js";

let taskRunning = false;

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
  pollAndRunNextTask().catch((error) => {
    console.warn("MRO extension task polling failed:", error);
  });
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message?.type === "MRO_SEND_HEARTBEAT") {
    sendHeartbeat()
      .then(async (result) => {
        const task = await pollAndRunNextTask();
        sendResponse({ ok: true, result, task });
      })
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "MRO_OPEN_PLATFORM_LOGIN") {
    openPlatformLogin(message.platform)
      .then(() => sendResponse({ ok: true }))
      .catch((error) => sendResponse({ ok: false, error: error.message }));
    return true;
  }
  if (message?.type === "MRO_POLL_TASK") {
    pollAndRunNextTask()
      .then((result) => sendResponse({ ok: true, result }))
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

async function pollAndRunNextTask() {
  if (taskRunning) return { skipped: true, reason: "task_running" };

  const settings = await getSettings();
  if (!settings.extToken) return { skipped: true, reason: "not_bound" };

  taskRunning = true;
  try {
    const task = await fetchNextTask(settings.apiBase, settings.extToken);
    if (!task) return { skipped: true, reason: "no_task" };

    const runner = getTaskRunner(task.platform);
    if (!runner) {
      await updateSubtaskStatus(
        settings.apiBase,
        settings.extToken,
        task.subtaskId,
        "failed",
        `平台适配器未实现：${task.platform}`,
      );
      return { skipped: false, subtaskId: task.subtaskId, status: "failed" };
    }

    const result = await runner(task);
    // 由纯函数 decideSubtaskOutcome 决定落库状态:done / login_required / failed。
    // login_required 是本次新增路径 —— 让"未登录拿到默认页"明确走登录引导,
    // 而不是把垃圾当 done 展示、或笼统标 failed。
    const outcome = decideSubtaskOutcome(result);
    if (outcome.status !== "done") {
      await updateSubtaskStatus(
        settings.apiBase,
        settings.extToken,
        task.subtaskId,
        outcome.status,
        outcome.message,
      );
      return { skipped: false, subtaskId: task.subtaskId, status: outcome.status };
    }

    await submitSubtaskResults(
      settings.apiBase,
      settings.extToken,
      task.subtaskId,
      task.platform,
      result.searchTerm,
      result.offers,
    );
    return {
      skipped: false,
      subtaskId: task.subtaskId,
      status: "done",
      offers: result.offers.length,
    };
  } finally {
    taskRunning = false;
  }
}

function getTaskRunner(platform) {
  if (platform === "jd") return runJdSearchTask;
  if (platform === "zkh") return runZkhSearchTask;
  return null;
}
