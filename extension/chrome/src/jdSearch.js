import { parseJdSearchPage } from "./jdParser.js";

const MAX_RESULTS_PER_TERM = 10;
const MIN_RESULTS_TO_STOP = 5;
const TERM_TIMEOUT_MS = 12000;

export async function runJdSearchTask(task) {
  const searchTerms = task.searchTerms || [];
  let lastSearchTerm = "";
  let lastError = "";

  for (const searchTerm of searchTerms) {
    lastSearchTerm = searchTerm;
    try {
      const result = await withTimeout(
        collectJdSearchResults(searchTerm),
        TERM_TIMEOUT_MS,
        `京东搜索超时：${searchTerm}`,
      );
      const offers = result.offers || [];
      if (offers.length >= MIN_RESULTS_TO_STOP) {
        return { searchTerm, offers };
      }
      if (offers.length > 0) {
        return { searchTerm, offers };
      }
      lastError = result.error || "京东未解析到搜索结果";
    } catch (error) {
      lastError = error.message || "京东搜索失败";
    }
  }

  return {
    searchTerm: lastSearchTerm,
    offers: [],
    error: lastError || "没有可用搜索词",
  };
}

async function collectJdSearchResults(searchTerm) {
  const tab = await chrome.tabs.create({
    url: buildJdSearchUrl(searchTerm),
    active: false,
  });
  let keepOpenForUserAction = false;
  try {
    await waitForTabLoad(tab.id, TERM_TIMEOUT_MS);
    await sleep(1200);
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: parseJdSearchPage,
      args: [MAX_RESULTS_PER_TERM],
    });
    const offers = result?.result || [];
    if (offers.length > 0) return { offers };

    const [diagnostics] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: detectJdSearchIssue,
    });
    const issue = diagnostics?.result || {};
    if (issue.requiresUserAction) {
      keepOpenForUserAction = true;
      await chrome.tabs.update(tab.id, { active: true }).catch(() => {});
      await chrome.storage.local.set({
        pendingJdVerification: {
          tabId: tab.id,
          url: issue.url || "",
          message: issue.message,
          searchTerm,
          createdAt: new Date().toISOString(),
        },
      });
    }
    return { offers, error: issue.message || "" };
  } finally {
    if (tab.id && !keepOpenForUserAction) {
      await chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
}

function detectJdSearchIssue() {
  const text = document.body?.innerText || "";
  const currentUrl = location.href;
  if (/passport\.jd\.com|\/login/.test(currentUrl) || /请登录|账户登录|扫码登录/.test(text)) {
    return {
      message: "京东需要登录。已保留京东页面，请完成登录后回到比价卡片重试。",
      requiresUserAction: true,
      url: currentUrl,
    };
  }
  if (/验证码|安全验证|滑块|风险|验证身份|verify|captcha/i.test(text + " " + currentUrl)) {
    return {
      message: "京东触发安全验证。已保留京东页面，请完成验证后回到比价卡片重试。",
      requiresUserAction: true,
      url: currentUrl,
    };
  }
  if (!/(^|\.)search\.jd\.com$/.test(location.hostname)) {
    return {
      message: "京东搜索页被重定向，可能触发平台风控。已保留页面，请检查后回到比价卡片重试。",
      requiresUserAction: true,
      url: currentUrl,
    };
  }
  return {
    message: "京东未解析到搜索结果，可能是页面结构变化或平台风控。",
    requiresUserAction: false,
    url: currentUrl,
  };
}

function buildJdSearchUrl(searchTerm) {
  return `https://search.jd.com/Search?keyword=${encodeURIComponent(searchTerm)}&enc=utf-8`;
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

function withTimeout(promise, timeoutMs, message) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(message)), timeoutMs);
    promise
      .then((value) => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch((error) => {
        clearTimeout(timer);
        reject(error);
      });
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
