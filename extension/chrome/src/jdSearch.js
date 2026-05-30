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
    return { offers, error: diagnostics?.result || "" };
  } finally {
    if (tab.id) {
      await chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
}

function detectJdSearchIssue() {
  const text = document.body?.innerText || "";
  const currentUrl = location.href;
  if (/passport\.jd\.com|\/login/.test(currentUrl) || /请登录|账户登录|扫码登录/.test(text)) {
    return "京东登录态失效，请在 Chrome 扩展中重新打开京东登录。";
  }
  if (/验证码|安全验证|滑块|风险|验证身份|verify|captcha/i.test(text + " " + currentUrl)) {
    return "京东触发安全验证，扩展暂时无法自动采集。请在浏览器完成验证后稍后重试。";
  }
  if (!/(^|\.)search\.jd\.com$/.test(location.hostname)) {
    return "京东搜索页被重定向，可能触发平台风控。";
  }
  return "京东未解析到搜索结果，可能是页面结构变化或平台风控。";
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
