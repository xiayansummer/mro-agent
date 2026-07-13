/**
 * 1688 搜索结果页解析器。
 *
 * ⚠️ 2026-07-13 用浏览器自动化读真实页(搜"外六角螺栓")校准得出的关键事实:
 * 1688 列表页 DOM **class 全混淆/为空、无 data-* 属性**(反爬),所以**不能靠 class 选择器**
 * (与 jd/zkh 不同),改用**结构 + 文本模式**:
 *  - 商品卡片 = 指向商品详情的 <a>(href 含 detail.1688.com / dj.1688.com / /offer/数字 / /数字.html)
 *    且卡片内含 alicdn 图。用 href 锚定单商品卡片,天然区隔广告 banner。
 *  - 标题 = 卡片内最长的中文文本节点。
 *  - 价格 = 卡片内 ¥[数字](区间取下限,否则起批单价)→ parsePrice。真实页多为单个起批价(如 ¥0.25)。
 *  - 起订量 = 卡片内 "N件起" 文本;**列表页常常没有**→有则取、没有留空(真起订量/阶梯档要进详情页,范围外)。
 *  - 过滤"广告"卡片。
 * 注:浏览器自动化工具出于隐私会屏蔽 href/outerHTML,但**扩展 content script 环境读得到完整 href**,
 * 所以用 href 锚定卡片在扩展里可行。线上准确度需装扩展后在真实页迭代(见 1688-calibrate.console.js)。
 */

const OFFER_HREF_RE = /detail\.1688\.com|dj\.1688\.com|1688\.com\/offer\/|\/\d{9,}\.html/i;
const PRICE_RE = /(?:¥|￥)\s*([\d.]+)(?:\s*[-~至]\s*([\d.]+))?/;
const MOQ_RE = /(\d+)\s*(件|个|套|米|千克|kg|双|只|条|包|箱|卷|张)\s*起(?:批|订|拍)?/;

/** 从价格文本抽起批价/区间下限。返回 {priceValue, priceText}。priceValue 是"起批价/区间下限",非批发底价。 */
export function parsePrice(text) {
  const raw = (text || "").trim();
  const m = raw.match(PRICE_RE);
  if (!m) return { priceValue: null, priceText: raw };
  const low = parseFloat(m[1]);
  const priceText = m[2] ? `¥${m[1]}-${m[2]}` : `¥${m[1]}`; // 规范化:统一半角、去空格
  return { priceValue: Number.isFinite(low) ? low : null, priceText };
}

/** 从卡片文本抽起订量,如 "100件起批"→"≥100件";无则空串。 */
export function parseMoq(text) {
  const m = (text || "").match(MOQ_RE);
  return m ? `≥${m[1]}${m[2]}` : "";
}

function longestChineseText(card) {
  let best = "";
  for (const el of card.querySelectorAll("*")) {
    if (el.children.length) continue;
    const t = (el.textContent || "").trim();
    if (/[一-龥]/.test(t) && t.length > best.length && !/^广告$|^立即查看$|^\d/.test(t)) best = t;
  }
  return best.slice(0, 100);
}

function cardImageUrl(card) {
  const img = card.querySelector("img[src*='alicdn'], img[data-src*='alicdn'], img");
  let src = img?.getAttribute("src") || img?.getAttribute("data-src") || "";
  if (src.startsWith("//")) src = "https:" + src;
  return src;
}

/** 解析当前搜索结果页 → {url, offers:[{title,priceValue,priceText,moq,imageUrl,productUrl,brand}], hasLoginWall, hasPriceSignal}。 */
export function parse1688SearchPage(limit = 10) {
  const seen = new Set();
  const offers = [];
  const cards = [...document.querySelectorAll("a[href]")].filter(
    (a) => OFFER_HREF_RE.test(a.href) && a.querySelector("img"),
  );
  for (const card of cards) {
    if (offers.length >= limit) break;
    // 广告卡片:含"广告"且取不到价格的跳过(有价格的推广位仍作为一条候选)
    if (/广告/.test(card.textContent || "") && parsePrice(card.textContent || "").priceValue == null) continue;
    const title = longestChineseText(card);
    if (!title) continue;
    const key = card.href || title;
    if (seen.has(key)) continue;
    seen.add(key);
    const { priceValue, priceText } = parsePrice(card.textContent || "");
    offers.push({
      title,
      priceValue,
      priceText,
      moq: parseMoq(card.textContent || ""),
      imageUrl: cardImageUrl(card),
      productUrl: card.href,
      brand: null,
    });
  }
  const bodyText = document.body?.innerText || "";
  return {
    url: location.href,
    offers,
    hasLoginWall: offers.length === 0 && /(亲[，,]\s*)?请登录|安全验证|滑动验证|拖动滑块/.test(bodyText),
    hasPriceSignal: offers.some((o) => o.priceValue != null),
  };
}

export function is1688SearchResultUrl(href) {
  return /1688\.com\/(selloffer\/offer_search|s\/)/i.test(href || "");
}

export function classify1688Page({ isSearchUrl, validOfferCount, hasLoginWall }) {
  if (hasLoginWall) return "login_required";
  if (isSearchUrl && validOfferCount > 0) return "ok";
  if (validOfferCount === 0) return "empty";
  return "ok";
}
