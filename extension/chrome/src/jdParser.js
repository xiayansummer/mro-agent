export function parseJdSearchPage(limit) {
  if (!isSearchResultPage()) return [];

  const cards = uniqueElements([
    ...document.querySelectorAll(
      [
        "[class*='goods']",
        "[class*='product']",
        "[class*='item']",
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
      imageUrl: extractImageUrl(card, link),
      rawRank: offers.length + 1,
      matchScore: 0,
      matchReasons: [],
    });

    if (offers.length >= limit) break;
  }
  return offers;

  function isSearchResultPage() {
    return (
      /(^|\.)search\.jd\.com$/.test(location.hostname)
      && /\/Search/.test(location.pathname)
    ) || (
      /(^|\.)i-search\.jd\.com$/.test(location.hostname)
      && /\/search/.test(location.pathname)
    );
  }

  function looksLikeProductCard(text) {
    if (text.length < 8) return false;
    return /¥|￥|\d+(?:\.\d+)?/.test(text) && /(加入购物车|自营|有货|库存|配送|品牌|型号|规格|件|个|盒|包)/.test(text);
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
    return /item\.jd\.com|mro\.jd\.com\/.*(?:item|product|sku)|\/\d+\.html|chat\.jd\.com\/index\.action.*[?&]pid=/.test(href);
  }

  function normalizeProductUrl(href) {
    const pidMatch = href.match(/[?&]pid=(\d{6,})/);
    if (pidMatch) return `https://item.jd.com/${pidMatch[1]}.html`;
    return href;
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
      const node = card.matches?.(selector) ? card : card.querySelector(selector);
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

  function extractImageUrl(card, link) {
    const fromCard = Array.from(card.querySelectorAll("img"))
      .map((node) => node.currentSrc || node.src || node.getAttribute("data-lazy-img") || node.getAttribute("data-original") || "")
      .map(normalizeImageUrl)
      .find(Boolean);
    if (fromCard) return fromCard;

    try {
      const url = new URL(link, location.origin);
      const raw = url.searchParams.get("imgUrl");
      if (raw) return normalizeImageUrl(decodeURIComponent(raw));
    } catch {
      // ignore invalid URLs
    }
    return undefined;
  }

  function normalizeImageUrl(value) {
    const raw = String(value || "").trim();
    if (!raw || raw.startsWith("data:")) return "";
    if (raw.startsWith("//")) return `https:${raw}`;
    if (/^https?:\/\//i.test(raw)) return raw;
    if (raw.startsWith("jfs/")) return `https://img10.360buyimg.com/n1/${raw}`;
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
