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
      .then((result) => {
        // 心跳成功立即反馈;任务轮询失败不应污染"心跳成功"的结果 —— 否则
        // popup 会误显示"状态上报失败",诱使用户无谓重新绑定。
        pollAndRunNextTask().catch((e) => console.warn("MRO poll after heartbeat failed:", e));
        sendResponse({ ok: true, result });
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
  let processed = 0;
  const MAX_PER_POLL = 20; // 防失控上限:一次轮询最多连续处理 20 个子任务
  try {
    // 连续 drain 队列直到没有待办。一个比价任务含 jd + zkh 两个子任务,若每次只
    // 抓一个,剩下的要等下一个心跳周期(分钟级延迟),这里一次性抓完。
    while (processed < MAX_PER_POLL) {
      const task = await fetchNextTask(settings.apiBase, settings.extToken);
      if (!task) break;
      processed += 1;

      const runner = getTaskRunner(task.platform);
      if (!runner) {
        await updateSubtaskStatus(
          settings.apiBase,
          settings.extToken,
          task.subtaskId,
          "failed",
          `平台适配器未实现：${task.platform}`,
        );
        continue;
      }

      const result = await runner(task);
      // 由纯函数 decideSubtaskOutcome 决定落库状态:done / login_required / failed。
      const outcome = decideSubtaskOutcome(result);
      if (outcome.status !== "done") {
        await updateSubtaskStatus(
          settings.apiBase,
          settings.extToken,
          task.subtaskId,
          outcome.status,
          outcome.message,
        );
        continue; // 继续 drain,不中断后续子任务
      }

      await submitSubtaskResults(
        settings.apiBase,
        settings.extToken,
        task.subtaskId,
        task.platform,
        result.searchTerm,
        result.offers,
      );
    }
    return { skipped: false, processed };
  } finally {
    taskRunning = false;
  }
}

function getTaskRunner(platform) {
  if (platform === "jd") return runJdSearchTask;
  if (platform === "zkh") return runZkhSearchTask;
  return null;
}
