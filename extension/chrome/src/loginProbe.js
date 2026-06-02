import { PLATFORMS, getPlatform } from "./platforms.js";

const PROBE_TIMEOUT_MS = 8000;
// SPA(尤其震坤行)登录态是异步渲染的:document complete 时用户名/头像往往还没出来。
// 探测时在页面内轮询等待登录特征出现,最多等这么久,避免"已登录被判未登录/未知"。
const LOGIN_SETTLE_TIMEOUT_MS = 5000;
const LOGIN_POLL_INTERVAL_MS = 300;

export async function collectLoginStatus() {
  const statuses = [];
  for (const platform of PLATFORMS) {
    statuses.push(await probePlatformLogin(platform));
  }
  return statuses;
}

export async function probePlatformLogin(platform) {
  const checkedAt = new Date().toISOString();
  try {
    const tab = await chrome.tabs.create({
      url: platform.probeUrl,
      active: false,
    });
    try {
      await waitForTabLoad(tab.id, PROBE_TIMEOUT_MS);
      const [result] = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: detectLoginInPage,
        args: [platform, LOGIN_SETTLE_TIMEOUT_MS, LOGIN_POLL_INTERVAL_MS],
      });
      return normalizeProbeResult(platform.id, checkedAt, result?.result);
    } finally {
      if (tab.id) {
        await chrome.tabs.remove(tab.id).catch(() => {});
      }
    }
  } catch (error) {
    return {
      platform: platform.id,
      checkedAt,
      message: `登录态未知：${error.message || "探测失败"}`,
    };
  }
}

export async function openPlatformLogin(platformId) {
  const platform = getPlatform(platformId);
  if (!platform) throw new Error(`unknown platform: ${platformId}`);
  await chrome.tabs.create({ url: platform.loginUrl, active: true });
}

/**
 * 把页面内采集到的原始信号(loggedInSignals / loggedOutSignals 命中计数)
 * 解释为三态登录结论。纯函数,不依赖 DOM,可被 node --test 单测。
 * - 登录信号出现且不弱于未登录信号 → 已登录
 * - 仅未登录信号 → 未登录
 * - 其它(无信号 / 信号矛盾)→ 无法判断(null),不轻易误判未登录
 */
export function interpretLoginSignals({ loggedInSignals, loggedOutSignals }) {
  if (loggedInSignals > 0 && loggedInSignals >= loggedOutSignals) {
    return { loggedIn: true, message: "检测到已登录特征" };
  }
  if (loggedOutSignals > 0 && loggedInSignals === 0) {
    return { loggedIn: false, message: "检测到未登录入口" };
  }
  return { loggedIn: null, message: "页面特征不足，无法判断登录态" };
}

function normalizeProbeResult(platformId, checkedAt, signals) {
  if (!signals) {
    return { platform: platformId, checkedAt, message: "登录态未知" };
  }
  const verdict = interpretLoginSignals(signals);
  if (verdict.loggedIn === null) {
    return { platform: platformId, checkedAt, message: verdict.message };
  }
  return {
    platform: platformId,
    loggedIn: verdict.loggedIn,
    checkedAt,
    message: verdict.message,
  };
}

function waitForTabLoad(tabId, timeoutMs) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      reject(new Error("页面加载超时"));
    }, timeoutMs);

    function listener(updatedTabId, changeInfo) {
      if (updatedTabId !== tabId || changeInfo.status !== "complete") return;
      clearTimeout(timer);
      chrome.tabs.onUpdated.removeListener(listener);
      resolve();
    }

    chrome.tabs.onUpdated.addListener(listener);
  });
}

// 注入页面执行,必须自包含(不能引用模块顶层函数)。
// 在页面内轮询等待登录态特征渲染出来,只返回原始命中计数,
// 判定交给 background 的 interpretLoginSignals。
async function detectLoginInPage(platform, settleTimeoutMs, pollIntervalMs) {
  function snapshot() {
    const text = document.body?.innerText || "";
    const hasSelector = (selectors) => (selectors || []).some((selector) => document.querySelector(selector));
    const hasText = (tokens) => (tokens || []).some((token) => text.includes(token));
    const loggedInSignals = [
      hasSelector(platform.loggedInSelectors),
      hasText(platform.loggedInText),
    ].filter(Boolean).length;
    const loggedOutSignals = [
      hasSelector(platform.loggedOutSelectors),
      hasText(platform.loggedOutText),
    ].filter(Boolean).length;
    return { loggedInSignals, loggedOutSignals };
  }

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const deadline = Date.now() + (settleTimeoutMs || 0);
  let snap = snapshot();

  // 等到出现"已登录"特征就提前结束;否则轮询到超时,给 SPA 异步渲染
  // 用户名/头像留足时间,减少"已登录 → 未知/未登录"的误判。
  while (Date.now() < deadline && snap.loggedInSignals === 0) {
    await sleep(pollIntervalMs || 300);
    snap = snapshot();
  }
  return snap;
}
