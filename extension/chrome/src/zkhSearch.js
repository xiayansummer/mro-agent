import { parseZkhSearchPage } from "./zkhParser.js";

const MAX_RESULTS_PER_TERM = 10;
const MIN_RESULTS_TO_STOP = 5;
const TERM_TIMEOUT_MS = 12000;

export async function runZkhSearchTask(task) {
  const searchTerms = task.searchTerms || [];
  let lastSearchTerm = "";
  let lastError = "";

  for (const searchTerm of searchTerms) {
    lastSearchTerm = searchTerm;
    try {
      const offers = await withTimeout(
        collectZkhSearchResults(searchTerm),
        TERM_TIMEOUT_MS,
        `震坤行搜索超时：${searchTerm}`,
      );
      if (offers.length >= MIN_RESULTS_TO_STOP) {
        return { searchTerm, offers };
      }
      if (offers.length > 0) {
        return { searchTerm, offers };
      }
      lastError = "未解析到搜索结果";
    } catch (error) {
      lastError = error.message || "震坤行搜索失败";
    }
  }

  return {
    searchTerm: lastSearchTerm,
    offers: [],
    error: lastError || "没有可用搜索词",
  };
}

async function collectZkhSearchResults(searchTerm) {
  const tab = await chrome.tabs.create({
    url: buildZkhSearchUrl(searchTerm),
    active: false,
  });
  try {
    await waitForTabLoad(tab.id, TERM_TIMEOUT_MS);
    await sleep(1800);
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: parseZkhSearchPage,
      args: [MAX_RESULTS_PER_TERM],
    });
    return result?.result || [];
  } finally {
    if (tab.id) {
      await chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
}

function buildZkhSearchUrl(searchTerm) {
  return `https://www.zkh.com/search.html?keywords=${encodeURIComponent(searchTerm)}`;
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
