import { PLATFORMS, getPlatform } from "./platforms.js";

const PROBE_TIMEOUT_MS = 8000;

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
        args: [platform],
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

function normalizeProbeResult(platformId, checkedAt, result) {
  if (!result || result.loggedIn === null) {
    return {
      platform: platformId,
      checkedAt,
      message: result?.message || "登录态未知",
    };
  }
  return {
    platform: platformId,
    loggedIn: result.loggedIn,
    checkedAt,
    message: result.message,
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

function detectLoginInPage(platform) {
  const text = document.body?.innerText || "";
  const hasSelector = (selectors) => selectors.some((selector) => document.querySelector(selector));
  const hasText = (tokens) => tokens.some((token) => text.includes(token));

  const loggedInSignals = [
    hasSelector(platform.loggedInSelectors || []),
    hasText(platform.loggedInText || []),
  ].filter(Boolean).length;

  const loggedOutSignals = [
    hasSelector(platform.loggedOutSelectors || []),
    hasText(platform.loggedOutText || []),
  ].filter(Boolean).length;

  if (loggedInSignals > 0 && loggedInSignals >= loggedOutSignals) {
    return { loggedIn: true, message: "检测到已登录特征" };
  }
  if (loggedOutSignals > 0 && loggedInSignals === 0) {
    return { loggedIn: false, message: "检测到未登录入口" };
  }
  return { loggedIn: null, message: "页面特征不足，无法判断登录态" };
}
