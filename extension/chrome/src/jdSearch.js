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
      const offers = await withTimeout(
        collectJdSearchResults(searchTerm),
        TERM_TIMEOUT_MS,
        `京东搜索超时：${searchTerm}`,
      );
      if (offers.length >= MIN_RESULTS_TO_STOP) {
        return { searchTerm, offers };
      }
      if (offers.length > 0) {
        return { searchTerm, offers };
      }
      lastError = "未解析到搜索结果";
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
    return result?.result || [];
  } finally {
    if (tab.id) {
      await chrome.tabs.remove(tab.id).catch(() => {});
    }
  }
}

function buildJdSearchUrl(searchTerm) {
  return `https://mro.jd.com/search?keyword=${encodeURIComponent(searchTerm)}`;
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

function parseJdSearchPage(limit) {
  const cards = Array.from(document.querySelectorAll(
    [
      "[class*='goods']",
      "[class*='product']",
      "[class*='item']",
      "li",
    ].join(","),
  ));

  const offers = [];
  const seen = new Set();
  for (const card of cards) {
    const text = compactText(card.innerText || "");
    if (!looksLikeProductCard(text)) continue;

    const link = firstProductLink(card);
    const title = extractTitle(card, text);
    if (!title || !link) continue;

    const id = `jd-${hashString(link)}-${offers.length + 1}`;
    if (seen.has(link) || seen.has(title)) continue;
    seen.add(link);
    seen.add(title);

    offers.push({
      id,
      platform: "jd",
      title,
      brand: extractBrand(text),
      specText: extractSpecText(text),
      priceText: extractPriceText(text),
      priceValue: extractPriceValue(text),
      currency: "CNY",
      unitText: extractUnitText(text),
      unitComparable: false,
      stockText: extractStockText(text),
      deliveryText: extractDeliveryText(text),
      productUrl: link,
      platformSku: extractSku(link, text),
      rawRank: offers.length + 1,
      matchScore: 0,
      matchReasons: [],
    });

    if (offers.length >= limit) break;
  }
  return offers;
}

function looksLikeProductCard(text) {
  if (text.length < 8) return false;
  return /¥|￥|\d+(?:\.\d+)?/.test(text) && /(加入购物车|自营|有货|库存|配送|品牌|型号|规格|件|个|盒|包)/.test(text);
}

function firstProductLink(card) {
  const link = Array.from(card.querySelectorAll("a[href]"))
    .map((node) => node.href)
    .find((href) => /item\.jd\.com|mro\.jd\.com\/.*(?:item|product|sku)|\/\d+\.html/.test(href));
  return link || "";
}

function extractTitle(card, fallbackText) {
  const selectors = [
    "[class*='title']",
    "[class*='name']",
    "[class*='sku']",
    "a[title]",
    "a",
  ];
  for (const selector of selectors) {
    const node = card.querySelector(selector);
    const value = compactText(node?.getAttribute("title") || node?.innerText || "");
    if (value && value.length >= 4 && !/登录|注册|购物车/.test(value)) {
      return value.slice(0, 160);
    }
  }
  return fallbackText.split(/\n|¥|￥/)[0].slice(0, 160);
}

function extractBrand(text) {
  const match = text.match(/品牌[:：\s]*([^\s｜|，,]+)/);
  return match?.[1] || undefined;
}

function extractSpecText(text) {
  const match = text.match(/(?:规格|型号|参数)[:：\s]*([^｜|，,\n]{2,80})/);
  return match?.[1]?.trim() || undefined;
}

function extractPriceText(text) {
  const match = text.match(/[¥￥]\s*\d+(?:\.\d+)?(?:\s*[-~]\s*\d+(?:\.\d+)?)?/);
  return match?.[0]?.replace(/\s+/g, "") || undefined;
}

function extractPriceValue(text) {
  const priceText = extractPriceText(text);
  if (!priceText) return undefined;
  const match = priceText.match(/\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : undefined;
}

function extractUnitText(text) {
  const match = text.match(/\/\s*(个|件|盒|包|支|套|米|卷|台|瓶|桶)/);
  return match?.[1] || undefined;
}

function extractStockText(text) {
  const match = text.match(/(现货|有货|无货|库存[^｜|，,\n]{0,20})/);
  return match?.[0] || undefined;
}

function extractDeliveryText(text) {
  const match = text.match(/(预计[^｜|，,\n]{0,30}|配送[^｜|，,\n]{0,30}|发货[^｜|，,\n]{0,30})/);
  return match?.[0] || undefined;
}

function extractSku(url, text) {
  const urlMatch = url.match(/(\d{6,})/);
  if (urlMatch) return urlMatch[1];
  const textMatch = text.match(/(?:SKU|编码|货号)[:：\s]*([A-Za-z0-9_-]{4,})/i);
  return textMatch?.[1] || undefined;
}

function compactText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function hashString(value) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = ((hash << 5) - hash + value.charCodeAt(index)) | 0;
  }
  return Math.abs(hash).toString(36);
}
