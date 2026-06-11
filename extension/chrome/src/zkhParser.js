export function parseZkhSearchPage(limit) {
  const pageUrl = location.href;
  const pageText = document.body?.innerText || "";
  const hasPriceSignal = /[¥￥]/.test(pageText);
  const hasLoginWall = detectLoginWall(pageText);

  const cards = uniqueElements([
    ...document.querySelectorAll(
      [
        "[class*='goods']",
        "[class*='product']",
        "[class*='item']",
        "[class*='sku']",
        "[class*='commodity']",
        "li",
      ].join(","),
    ),
    ...productLinkElements(),
  ]);

  const offers = [];
  const seen = new Set();
  for (const card of cards) {
    const text = compactText(card.innerText || "");
    if (!looksLikeProductCard(text)) continue;

    const link = firstProductLink(card);
    const title = extractTitle(card, text);
    if (!title || !link) continue;

    // 同 jdParser:id 只由链接 hash 决定,跨任务稳定,保证"不合适"抑制可靠。
    const id = `zkh-${hashString(link)}`;
    if (seen.has(link) || seen.has(title)) continue;
    seen.add(link);
    seen.add(title);

    offers.push({
      id,
      platform: "zkh",
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
      imageUrl: extractImageUrl(card),
      rawRank: offers.length + 1,
      matchScore: 0,
      matchReasons: [],
    });

    if (offers.length >= limit) break;
  }
  return { url: pageUrl, offers, hasLoginWall, hasPriceSignal };

  function detectLoginWall(text) {
    // 震坤行未登录/被拦截时常见的登录引导短语。用较强短语避免已登录页里
    // 普通"登录"链接造成误判。⚠️ 具体短语需用真实未登录页样本最终校准
    // (见 scripts/zkh-calibrate.console.js)。
    return /请登录|登录后查看|登录查看|您(还|尚)未登录|未登录|立即登录|登录\/注册/.test(text);
  }

  function looksLikeProductCard(text) {
    if (text.length < 8) return false;
    return /¥|￥|\d+(?:\.\d+)?/.test(text) && /(加入购物车|购物车|现货|库存|品牌|型号|规格|货号|订货号|件|个|盒|包|台)/.test(text);
  }

  function productLinkElements() {
    return Array.from(document.querySelectorAll("a[href]"))
      .filter((node) => isProductHref(node.href));
  }

  function uniqueElements(elements) {
    const seenElements = new Set();
    return elements.filter((element) => {
      if (seenElements.has(element)) return false;
      seenElements.add(element);
      return true;
    });
  }

  function firstProductLink(card) {
    if (card.matches?.("a[href]") && isProductHref(card.href)) return normalizeProductUrl(card.href);
    const link = Array.from(card.querySelectorAll("a[href]"))
      .map((node) => node.href)
      .find(isProductHref);
    return link ? normalizeProductUrl(link) : "";
  }

  function isProductHref(href) {
    return /zkh\.com\/.*(product|goods|item|sku|detail)|\/p\/|\/product\/|skuCode=|skuNo=|itemCode=|goodsCode=/.test(href);
  }

  function normalizeProductUrl(href) {
    try {
      const url = new URL(href, location.origin);
      url.hash = "";
      return url.toString();
    } catch {
      return href;
    }
  }

  function extractTitle(card, fallbackText) {
    const selectors = [
      "a[title]",
      "[class*='title']",
      "[class*='name']",
      "[class*='product']",
      "[class*='goods']",
      "[class*='commodity']",
      "a",
    ];
    for (const selector of selectors) {
      const node = card.matches?.(selector) ? card : card.querySelector(selector);
      const value = compactText(node?.getAttribute("title") || node?.innerText || "");
      if (looksLikeTitle(value)) {
        return value.slice(0, 160);
      }
    }
    const fallback = fallbackText
      .split(/¥|￥|加入购物车|购物车|现货|库存/)
      .map(compactText)
      .find(looksLikeTitle);
    return (fallback || "").slice(0, 160);
  }

  function looksLikeTitle(value) {
    const text = compactText(value);
    if (text.length < 4) return false;
    if (/登录|注册|购物车|客服|订货编码|订货号|货号|SKU|编码[:：]|品牌[:：]|型号[:：]|规格[:：]/i.test(text)) return false;
    if (/^[A-Z]{1,4}\d{4,}$/i.test(text)) return false;
    return /[\u4e00-\u9fa5A-Za-z]/.test(text);
  }

  function extractBrand(text) {
    const match = text.match(/品牌[:：\s]*([^\s｜|，,]+)/);
    if (match?.[1]) return match[1];
    if (/诺霸|NORBAR/i.test(text)) return "诺霸";
    if (/美和|TOHO/i.test(text)) return "美和";
    return undefined;
  }

  function extractSpecText(text) {
    const match = text.match(/(?:规格|型号|参数|订货号|货号)[:：\s]*([^｜|，,\n]{2,80})/);
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
    const match = text.match(/\/\s*(个|件|盒|包|支|套|米|卷|台|瓶|桶|只|把|根)/);
    return match?.[1] || undefined;
  }

  function extractStockText(text) {
    const match = text.match(/(现货|有货|无货|库存[^｜|，,\n]{0,20}|可售[^｜|，,\n]{0,20})/);
    return match?.[0] || undefined;
  }

  function extractDeliveryText(text) {
    const match = text.match(/(预计[^｜|，,\n]{0,30}|配送[^｜|，,\n]{0,30}|发货[^｜|，,\n]{0,30}|货期[^｜|，,\n]{0,30})/);
    return match?.[0] || undefined;
  }

  function extractSku(url, text) {
    const urlMatch = url.match(/[?&](?:skuCode|skuNo|itemCode|goodsCode)=([A-Za-z0-9_-]{4,})/i);
    if (urlMatch) return urlMatch[1];
    const textMatch = text.match(/(?:SKU|编码|货号|订货号)[:：\s]*([A-Za-z0-9_-]{4,})/i);
    return textMatch?.[1] || undefined;
  }

  function extractImageUrl(card) {
    return Array.from(card.querySelectorAll("img"))
      .map((node) => node.currentSrc || node.src || node.getAttribute("data-src") || node.getAttribute("data-original") || node.getAttribute("lazy-src") || "")
      .map(normalizeImageUrl)
      .find(Boolean) || undefined;
  }

  function normalizeImageUrl(value) {
    const raw = String(value || "").trim();
    if (!raw || raw.startsWith("data:")) return "";
    if (raw.startsWith("//")) return `https:${raw}`;
    try {
      return new URL(raw, location.origin).toString();
    } catch {
      return "";
    }
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
}

// ───────────────────────────────────────────────────────────────────
// 以下为 background 侧的纯判定函数(不依赖 document,可被 node --test 单测)。
// parseZkhSearchPage 注入页面执行时是自包含的,不引用这些函数;
// zkhSearch.js 采集到信号后调用它们做判定。
// ───────────────────────────────────────────────────────────────────

/**
 * 收紧的"震坤行真实搜索结果页"URL 判定。
 * 必须是 zkh.com 主域(排除 passport 等登录子域)、search 路径、且带 keyword(s) 参数。
 * 旧逻辑 /(search|product|goods|sku|item)/ 过宽,未登录被打回的页面也可能命中。
 */
export function isZkhSearchResultUrl(href) {
  let url;
  try {
    url = new URL(href);
  } catch {
    return false;
  }
  if (!/(^|\.)zkh\.com$/i.test(url.hostname)) return false;
  if (/(^|\.)passport\.zkh\.com$/i.test(url.hostname)) return false;
  if (!/search/i.test(url.pathname)) return false;
  return url.searchParams.has("keywords") || url.searchParams.has("keyword");
}

/**
 * 识别"订货编码"占位标题。震坤行未登录/默认页抓到的"商品"标题常是
 * "订货编码:AExxxx" 或裸编码,而非真实商品名 —— 这类不应计为有效结果。
 */
export function isOrderCodePlaceholder(text) {
  const value = String(text || "").trim();
  if (!value) return false;
  if (/^订货编码\s*[:：]/.test(value)) return true;
  if (/^[A-Z]{1,4}\d{4,}$/i.test(value)) return true;
  return false;
}

/**
 * 综合页面信号 → 'results' | 'login_required' | 'empty'。
 * - 非搜索 URL(被重定向)→ 需要登录
 * - 有有效商品 → 结果
 * - 有登录墙 → 需要登录
 * - 无有效商品 + 无价格语义(疑似默认/拦截页)→ 需要登录
 * - 真搜索页、无登录墙、有价格语义但无匹配 → 空结果
 */
export function classifyZkhPage({ isSearchUrl, validOfferCount, hasLoginWall, hasPriceSignal }) {
  if (!isSearchUrl) return "login_required";
  if (validOfferCount > 0) return "results";
  if (hasLoginWall) return "login_required";
  if (!hasPriceSignal) return "login_required";
  return "empty";
}
