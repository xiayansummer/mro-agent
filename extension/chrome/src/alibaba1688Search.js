import { parse1688SearchPage, is1688SearchResultUrl, classify1688Page } from "./alibaba1688Parser.js";
import { hasBrandMatch, normalizeRequiredBrand } from "./brandMatch.js";

const MAX_RESULTS_PER_TERM = 10;
const TERM_TIMEOUT_MS = 15000; // 1688 页较重、结果异步渲染,比 jd/zkh 略放宽

export async function run1688SearchTask(task) {
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
        collect1688(searchTerm),
        TERM_TIMEOUT_MS,
        `1688 搜索超时：${searchTerm}`,
      );
      const offers = page.offers || [];
      const verdict = classify1688Page({
        isSearchUrl: is1688SearchResultUrl(page.url),
        validOfferCount: offers.length,
        hasLoginWall: page.hasLoginWall,
      });

      if (verdict === "login_required") {
        loginRequired = true;
        lastError = "1688 登录态未知或被要求登录/验证,未取到真实搜索结果";
        continue;
      }
      if (requiredBrand && offers.length > 0 && !hasBrandMatch(offers, requiredBrand)) {
        bestPartial ??= { searchTerm, offers };
        lastError = `1688 搜索词「${searchTerm}」未命中品牌「${requiredBrand}」,继续尝试更宽泛搜索词`;
        continue;
      }
      if (offers.length > 0) {
        return { searchTerm, offers };
      }
      lastError = "未解析到搜索结果";
    } catch (error) {
      lastError = error.message || "1688 搜索失败";
    }
  }

  if (loginRequired && !bestPartial) {
    return {
      searchTerm: lastSearchTerm,
      offers: [],
      error: "1688 登录态未知,请在扩展完成登录后重试",
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

async function collect1688(searchTerm) {
  // ⚠️ 2026-07-13 实测:s.1688.com 搜索页按 **GBK** 解 keywords,直接用 UTF-8(encodeURIComponent)
  // 的 URL 会乱码→0 结果。扩展纯 JS 无内置 GBK 编码,故打开搜索页后**在页面里用搜索框输入+提交**,
  // 让页面自身按其 charset 正确编码,规避 GBK URL 问题。(搜索框 id=alisearch-input,实测。)
  const tab = await chrome.tabs.create({
    url: "https://s.1688.com/selloffer/offer_search.htm",
    active: false,
  });
  try {
    await waitForTabLoad(tab.id, TERM_TIMEOUT_MS);
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: submitSearchInPage,
      args: [searchTerm],
    });
    await sleep(2600); // 等搜索提交后结果页渲染(1688 结果异步)
    const [result] = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: parse1688SearchPage,
      args: [MAX_RESULTS_PER_TERM],
    });
    return result?.result || { url: "", offers: [], hasLoginWall: false, hasPriceSignal: false };
  } finally {
    if (tab.id) {
      await chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
}

// 在页面上下文执行:把搜索词填进搜索框并触发搜索(页面按自身 charset 编码提交)。
function submitSearchInPage(term) {
  const box = document.querySelector("#alisearch-input, input[name='keywords'], input.ali-search-input");
  if (!box) return;
  box.value = term;
  box.dispatchEvent(new Event("input", { bubbles: true }));
  const btn = [...document.querySelectorAll("button, a, input[type='submit']")].find(
    (b) => /搜\s*索|search/i.test(b.textContent || b.value || ""),
  );
  if (btn) btn.click();
  else box.closest("form")?.submit();
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
