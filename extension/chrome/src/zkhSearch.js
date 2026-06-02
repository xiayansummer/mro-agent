import {
  parseZkhSearchPage,
  isZkhSearchResultUrl,
  isOrderCodePlaceholder,
  classifyZkhPage,
} from "./zkhParser.js";
import { hasBrandMatch, normalizeRequiredBrand } from "./brandMatch.js";

const MAX_RESULTS_PER_TERM = 10;
const TERM_TIMEOUT_MS = 12000;

export async function runZkhSearchTask(task) {
  const searchTerms = task.searchTerms || [];
  const requiredBrand = normalizeRequiredBrand(task.requiredBrand);
  let lastSearchTerm = "";
  let lastError = "";
  let bestPartial = null;
  let loginRequired = false;

  for (const searchTerm of searchTerms) {
    lastSearchTerm = searchTerm;
    try {
      const page = await withTimeout(
        collectZkhSearchResults(searchTerm),
        TERM_TIMEOUT_MS,
        `震坤行搜索超时：${searchTerm}`,
      );
      // 先剔除"订货编码"占位(未登录/默认页特征),再综合判定页面类型
      const offers = (page.offers || []).filter((offer) => !isOrderCodePlaceholder(offer.title));
      const verdict = classifyZkhPage({
        isSearchUrl: isZkhSearchResultUrl(page.url),
        validOfferCount: offers.length,
        hasLoginWall: page.hasLoginWall,
        hasPriceSignal: page.hasPriceSignal,
      });

      if (verdict === "login_required") {
        // 关键修复:未登录/默认页不再把"订货编码"垃圾当结果返回,
        // 而是标记登录态问题,交由 background 落成 login_required。
        loginRequired = true;
        lastError = "震坤行登录态未知或被要求登录,未取到真实搜索结果";
        continue;
      }

      if (requiredBrand && offers.length > 0 && !hasBrandMatch(offers, requiredBrand)) {
        bestPartial ??= { searchTerm, offers };
        lastError = `震坤行搜索词「${searchTerm}」未命中品牌「${requiredBrand}」,继续尝试更宽泛搜索词`;
        continue;
      }
      if (offers.length > 0) {
        return { searchTerm, offers };
      }
      lastError = "未解析到搜索结果";
    } catch (error) {
      lastError = error.message || "震坤行搜索失败";
    }
  }

  if (loginRequired && !bestPartial) {
    return {
      searchTerm: lastSearchTerm,
      offers: [],
      error: "震坤行登录态未知,请在扩展完成登录后重试",
      loginRequired: true,
    };
  }
  if (bestPartial) return bestPartial;
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
    return result?.result || { url: "", offers: [], hasLoginWall: false, hasPriceSignal: false };
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
