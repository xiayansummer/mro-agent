import { PLATFORMS, getPlatform } from "./platforms.js";
import { LOGIN_PROBE_TTL_MINUTES } from "./config.js";

const PROBE_TIMEOUT_MS = 8000;
// SPA(尤其震坤行)登录态是异步渲染的:document complete 时用户名/头像往往还没出来。
// 探测时在页面内轮询等待登录特征出现,最多等这么久,避免"已登录被判未登录/未知"。
const LOGIN_SETTLE_TIMEOUT_MS = 5000;
const LOGIN_POLL_INTERVAL_MS = 300;
const LOGIN_CACHE_KEY = "loginStatusCache";

async function readLoginCache() {
  const stored = await chrome.storage.local.get([LOGIN_CACHE_KEY]);
  return stored[LOGIN_CACHE_KEY] || {};
}

async function writeLoginCacheEntry(platformId, status) {
  const cache = await readLoginCache();
  cache[platformId] = { status, ts: Date.now() };
  await chrome.storage.local.set({ [LOGIN_CACHE_KEY]: cache });
}

// 纯函数,便于单测:缓存项是否仍在 TTL 内。
export function isCacheFresh(ts, now, ttlMs) {
  return typeof ts === "number" && now - ts < ttlMs;
}

/**
 * 收集各平台登录态。**关键:探测会真打开京东/震坤行页面**,每分钟心跳都探会触发
 * 平台风控。因此默认走 TTL 缓存:每个平台最多每 LOGIN_PROBE_TTL_MINUTES 分钟才
 * 真打开一次平台页探测,TTL 内复用上次结果、不开页。真实搜索任务也会经
 * recordPlatformLoginFromTask 刷新缓存,活跃使用期间几乎无需主动探测。
 * force=true(手动「立即上报状态」)时绕过 TTL、强制即时探测。
 */
export async function collectLoginStatus(force = false) {
  const ttlMs = LOGIN_PROBE_TTL_MINUTES * 60 * 1000;
  const cache = await readLoginCache();
  const now = Date.now();
  const statuses = [];
  for (const platform of PLATFORMS) {
    const cached = cache[platform.id];
    if (!force && cached?.status && isCacheFresh(cached.ts, now, ttlMs)) {
      statuses.push(cached.status); // 复用缓存,不打开平台页
      continue;
    }
    const status = await probePlatformLogin(platform);
    await writeLoginCacheEntry(platform.id, status);
    statuses.push(status);
  }
  return statuses;
}

/**
 * 真实搜索任务已加载过平台搜索页、天然知道登录态,把结果回写缓存:
 * 让活跃使用期间的心跳直接复用、无需再主动探测,进一步收窄风控触发面。
 * loggedIn=true → 搜到结果即已登录;false → 命中登录/验证拦截。
 */
export async function recordPlatformLoginFromTask(platformId, loggedIn, message) {
  if (!getPlatform(platformId)) return;
  await writeLoginCacheEntry(platformId, {
    platform: platformId,
    loggedIn,
    checkedAt: new Date().toISOString(),
    message: message || (loggedIn ? "搜索任务确认已登录" : "搜索任务检测到未登录/验证拦截"),
  });
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
