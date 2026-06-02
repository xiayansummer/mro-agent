export function parseZkhSearchPage(limit) {
  if (!isSearchResultPage()) return [];

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

    const id = `zkh-${hashString(link)}-${offers.length + 1}`;
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
  return offers;

  function isSearchResultPage() {
    return (
      /(^|\.)zkh\.com$/.test(location.hostname)
      && /(search|product|goods|sku|item)/i.test(location.href)
    );
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
