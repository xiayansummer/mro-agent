/**
 * 1688 搜索结果页解析器。
 *
 * ⚠️ 2026-07-13 用浏览器自动化 + 真机端到端校准得出的关键事实:
 * 1688 列表页 DOM **class 全混淆/为空、无 data-* 属性、img alt/title 也空**(反爬),所以
 * **不能靠 class 选择器**(与 jd/zkh 不同),改用**结构 + 文本模式**:
 *  - 商品卡片 = 指向商品详情的 <a>(href 含 detail.1688.com / dj.1688.com / /offer/数字 / /数字.html)
 *    且卡片内含 alicdn 图。用 href 锚定单商品卡片,天然区隔广告 banner。
 *  - 价格被拆成 ¥/整数/小数 多个相邻文本节点;标题恒在价格节点之前、成交计数/物流标签恒在其后。
 *    故标题 = 价格节点前的非噪声叶子拼接;价格 = 从 ¥ 节点起拼接紧邻纯数字片段。
 *  - 起订量列表页常无 → 有则取、无则空(真起订量/阶梯档要进详情页,范围外)。
 *
 * 架构(关键):**DOM 采集与解析分离**。
 *  - `collect1688RawCards` 注入页面执行(chrome.scripting.executeScript 只序列化本函数源码,
 *    引用模块作用域会在页面里 ReferenceError——jd/zkh 的注入函数都自包含就是这个原因),
 *    因此它**自包含、只做 DOM 采集**,返回每卡的原始 {leaves,href,imageUrl} + 页面元信息。
 *  - `parse1688SearchPage` 在**后台(扩展上下文)**跑,吃 collect 的原始数据、用下面这些模块级
 *    纯函数(可单测)产出 offer。这样校准逻辑(extractTitle/extractPriceText 等)有单测、且不重复。
 */

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

// 噪声叶子:促销/物流标签、公司名、成交计数、百分比、分隔符。实测这些混在标题区之外,
// 用于把它们从标题里剔除。注意不按"以数字开头"排除——商品名常以数字/型号打头(如"304不锈钢…")。
export function isNoiseLeaf(t) {
  return (
    !t ||
    t === "｜" ||
    t === "|" ||
    /^(好评率|回头率|全网|月浏览|浏览|退货|包邮|包运费|先采后付|先采|代发|定制|广告|立即|已售|复购|明天达|支持|下单|旺旺|在线|口碑|品牌|图片|视频)/.test(t) ||
    /(有限公司|制造厂|经营部|商行|工厂|旗舰店|专营店|专卖店|五金厂)$/.test(t) ||
    /^\d[\d.]*(万|亿|\+)*\s*件$/.test(t) || // 成交计数 "1500+件"/"10万+件"
    /^\d+(\.\d+)?%$/.test(t) // 百分比
  );
}

// 标题 = 价格节点(¥)之前的非噪声叶子拼接。实测 1688 列表页把标题排在价格前、成交计数/物流
// 标签排在价格后,故以价格节点为结构边界能天然排除"1500+件/月浏览1000+"等尾部计数,
// 无需逐类特判。标题可能被拆成多个纯中文碎片(如"六角"+"螺栓"),相邻纯中文段无缝拼接;
// 规格段(如"10B21(碳钢)""8.8级")用空格分隔以保留可读性并区分同名商品。
export function extractTitle(leaves) {
  let priceIdx = leaves.findIndex((t) => /[¥￥]/.test(t));
  if (priceIdx < 0) priceIdx = leaves.length;
  const parts = [];
  for (let i = 0; i < priceIdx; i += 1) {
    const t = leaves[i];
    if (isNoiseLeaf(t)) continue;
    if (!/[一-龥A-Za-z0-9]/.test(t)) continue; // 跳过纯符号
    parts.push(t);
  }
  if (!parts.length) return "";
  let title = parts[0];
  for (let k = 1; k < parts.length; k += 1) {
    const prevPureCn = /^[一-龥]+$/.test(parts[k - 1]);
    const curPureCn = /^[一-龥]+$/.test(parts[k]);
    title += prevPureCn && curPureCn ? parts[k] : ` ${parts[k]}`;
  }
  return title.slice(0, 100);
}

// 价格 = 1688 把价格拆成 "¥" / 整数 / 小数 多个相邻文本节点(实测 ¥|0|.05)。
// 从 ¥ 节点起,拼接紧邻的纯数字/小数片段;遇非数字节点(如"全网10万+件")即停,避免粘连销量。
// 返回可交给 parsePrice 的价格字符串(如 "¥0.05"),取不到返回 ""。
export function extractPriceText(leaves) {
  const i = leaves.findIndex((t) => /[¥￥]/.test(t));
  if (i < 0) return "";
  let s = leaves[i];
  for (let j = i + 1; j < leaves.length; j += 1) {
    if (/^[.\d]+$/.test(leaves[j])) s += leaves[j];
    else break;
  }
  return s;
}

/**
 * 注入页面执行:只做 DOM 采集,返回 {url, cards:[{leaves,href,imageUrl}], hasLoginWall}。
 * **必须自包含**(不引用任何模块级符号)——executeScript 只序列化本函数源码,页面里没有模块作用域。
 * 解析(标题/价格/起订量)交给后台的 parse1688SearchPage,便于单测且不重复逻辑。
 */
export function collect1688RawCards(limit = 10) {
  const OFFER_HREF_RE = /detail\.1688\.com|dj\.1688\.com|1688\.com\/offer\/|\/\d{9,}\.html/i;
  const leafTexts = (card) =>
    [...card.querySelectorAll("*")]
      .filter((el) => !el.children.length)
      .map((el) => (el.textContent || "").trim())
      .filter(Boolean);
  const imageUrlOf = (card) => {
    const img = card.querySelector("img[src*='alicdn'], img[data-src*='alicdn'], img");
    let src = (img && (img.getAttribute("src") || img.getAttribute("data-src"))) || "";
    if (src.startsWith("//")) src = "https:" + src;
    return src;
  };
  const anchors = [...document.querySelectorAll("a[href]")].filter(
    (a) => OFFER_HREF_RE.test(a.href) && a.querySelector("img"),
  );
  const cards = [];
  for (const a of anchors) {
    if (cards.length >= limit * 2) break; // 多采些,去重/上限后台再收
    cards.push({ leaves: leafTexts(a), href: a.href, imageUrl: imageUrlOf(a) });
  }
  const bodyText = (document.body && document.body.innerText) || "";
  return {
    url: location.href,
    cards,
    hasLoginWall: /(亲[，,]\s*)?请登录|安全验证|滑动验证|拖动滑块/.test(bodyText),
  };
}

// 从商品 href 里取 1688 offerId(如 detail.1688.com/offer/626xxxxx.html 里的数字)作稳定 id;
// 取不到用 rank 兜底。dedup 已按 href 去重,这里只需稳定可辨识。
export function offer1688Id(href, rank) {
  const m = (href || "").match(/(\d{6,})/);
  return m ? `1688-${m[1]}` : `1688-${rank}`;
}

/**
 * 后台解析:吃 collect1688RawCards 的原始数据 → {url, offers, hasLoginWall, hasPriceSignal}。
 * offer 为完整 ExternalOffer 形状(id/platform/unitComparable/rawRank/matchScore/minOrderQty…),
 * 与后端严校验一致。纯数据入参、无 DOM,可单测。
 */
export function parse1688SearchPage(raw, limit = 10) {
  const cards = (raw && raw.cards) || [];
  const seen = new Set();
  const offers = [];
  for (const card of cards) {
    if (offers.length >= limit) break;
    const leaves = card.leaves || [];
    const title = extractTitle(leaves);
    if (!title) continue;
    const key = card.href || title;
    if (seen.has(key)) continue;
    seen.add(key);
    const { priceValue, priceText } = parsePrice(extractPriceText(leaves));
    const moq = parseMoq(leaves.join(" "));
    const rank = offers.length + 1;
    // 必须产出完整 ExternalOffer 形状(后端 SubmitSubtaskResultsRequest 按 ExternalOffer 严校验,
    // 缺 id/platform/unitComparable/rawRank/matchScore 会 422 → 回传失败、子任务卡 in_progress)。
    // 起批价不可做单位价比较 → unitComparable=false;起订量放专用字段 minOrderQty。
    offers.push({
      id: offer1688Id(card.href, rank),
      platform: "1688",
      title,
      brand: null,
      priceText,
      priceValue,
      currency: "CNY",
      unitComparable: false,
      minOrderQty: moq || null,
      productUrl: card.href || "",
      imageUrl: card.imageUrl || "",
      rawRank: rank,
      matchScore: 0,
      matchReasons: [],
    });
  }
  return {
    url: (raw && raw.url) || "",
    offers,
    // 登录墙只在完全没抓到 offer 时才断言(有 offer 说明页面正常渲染了结果)。
    hasLoginWall: offers.length === 0 && !!(raw && raw.hasLoginWall),
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
