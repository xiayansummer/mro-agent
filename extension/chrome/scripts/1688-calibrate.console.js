// 1688 校准脚本。用法:在真实 1688 页的 DevTools Console 里粘贴运行。
//   - 在搜索结果页(s.1688.com/selloffer/offer_search.htm?keywords=...)运行 → 校准商品提取。
//   - 在首页(www.1688.com,分别在已登录/未登录态)运行 → 校准 platforms.js 的登录态选择器。
// 提取逻辑与 alibaba1688Parser.js 完全一致(2026-07-13 已用浏览器自动化校准通过)。
//
// ⚠️ 1688 列表页 class 全混淆、无 data-*,故靠 href 锚定卡片 + 文本模式,不靠 class(见 parser 注释)。
// ⚠️ 关键结构(实测):价格被拆成 ¥/整数/小数 多个相邻文本节点;标题恒在价格节点之前、
//    成交计数/物流标签恒在其后 —— 故以 ¥ 节点为边界能天然区分标题与尾部计数。
(() => {
  const OFFER_HREF_RE = /detail\.1688\.com|dj\.1688\.com|1688\.com\/offer\/|\/\d{9,}\.html/i;
  const PRICE_RE = /(?:¥|￥)\s*([\d.]+)(?:\s*[-~至]\s*([\d.]+))?/;
  const MOQ_RE = /(\d+)\s*(件|个|套|米|千克|kg|双|只|条|包|箱|卷|张)\s*起(?:批|订|拍)?/;

  const leafTexts = (card) =>
    [...card.querySelectorAll("*")]
      .filter((el) => !el.children.length)
      .map((el) => (el.textContent || "").trim())
      .filter(Boolean);
  const isNoiseLeaf = (t) =>
    !t ||
    t === "｜" ||
    t === "|" ||
    /^(好评率|回头率|全网|月浏览|浏览|退货|包邮|包运费|先采后付|先采|代发|定制|广告|立即|已售|复购|明天达|支持|下单|旺旺|在线|口碑|品牌|图片|视频)/.test(t) ||
    /(有限公司|制造厂|经营部|商行|工厂|旗舰店|专营店|专卖店|五金厂)$/.test(t) ||
    /^\d[\d.]*(万|亿|\+)*\s*件$/.test(t) ||
    /^\d+(\.\d+)?%$/.test(t);
  const extractTitle = (leaves) => {
    let p = leaves.findIndex((t) => /[¥￥]/.test(t));
    if (p < 0) p = leaves.length;
    const parts = [];
    for (let i = 0; i < p; i += 1) {
      const t = leaves[i];
      if (isNoiseLeaf(t) || !/[一-龥A-Za-z0-9]/.test(t)) continue;
      parts.push(t);
    }
    if (!parts.length) return "";
    let title = parts[0];
    for (let k = 1; k < parts.length; k += 1) {
      const a = /^[一-龥]+$/.test(parts[k - 1]);
      const b = /^[一-龥]+$/.test(parts[k]);
      title += a && b ? parts[k] : ` ${parts[k]}`;
    }
    return title.slice(0, 100);
  };
  const extractPriceText = (leaves) => {
    const i = leaves.findIndex((t) => /[¥￥]/.test(t));
    if (i < 0) return "";
    let s = leaves[i];
    for (let j = i + 1; j < leaves.length; j += 1) {
      if (/^[.\d]+$/.test(leaves[j])) s += leaves[j];
      else break;
    }
    return s;
  };

  const isSearchPage = /selloffer\/offer_search|1688\.com\/s\//.test(location.href);
  if (isSearchPage) {
    const cards = [...document.querySelectorAll("a[href]")].filter(
      (a) => OFFER_HREF_RE.test(a.href) && a.querySelector("img"),
    );
    console.log(
      "%c命中商品卡片数: " + cards.length,
      "font-weight:bold",
      "(应与页面商品数接近;偏少→OFFER_HREF_RE 要补新详情 URL 模式,0→GBK 编码或登录墙)",
    );
    const seen = new Set();
    let shown = 0;
    for (const c of cards) {
      if (shown >= 8) break;
      const leaves = leafTexts(c);
      const title = extractTitle(leaves);
      if (!title) continue;
      const key = c.href || title;
      if (seen.has(key)) continue;
      seen.add(key);
      shown += 1;
      console.log(`#${shown}`, {
        title,
        price: (extractPriceText(leaves).match(PRICE_RE) || [])[0] || "(未匹配)",
        moq: (leaves.join(" ").match(MOQ_RE) || [])[0] || "(列表页无,正常)",
        img: (c.querySelector("img")?.src || "").slice(0, 55),
      });
    }
    console.log("核对:title 是否为商品名(非计数/公司名)?price 是否干净(非粘连)?price 是起批价(非批发底价)。");
  } else {
    // 登录态选择器校准:在已登录/未登录首页分别运行,核对哪些命中。
    const S = {
      loggedInSelectors: [".member-name", ".login-info-name", "[class*='member'] [class*='name']", "a[href*='work.1688.com']", "a[href*='member.1688.com']"],
      loggedOutSelectors: ["a[href*='login.1688.com']", "a[href*='signin']"],
      loggedInText: ["退出", "我的阿里", "采购车", "买家中心", "卖家中心"],
      loggedOutText: ["亲，请登录", "请登录", "免费注册"],
    };
    const body = document.body?.innerText || "";
    const hit = (sels) => sels.filter((s) => { try { return document.querySelector(s); } catch { return false; } });
    const txt = (words) => words.filter((w) => body.includes(w));
    console.log("%c登录态选择器校准(在首页运行)", "font-weight:bold");
    console.log("loggedInSelectors 命中:", hit(S.loggedInSelectors));
    console.log("loggedOutSelectors 命中:", hit(S.loggedOutSelectors));
    console.log("loggedInText 命中:", txt(S.loggedInText));
    console.log("loggedOutText 命中:", txt(S.loggedOutText));
    console.log("核对:已登录页应只命中 loggedIn* ;未登录页应只命中 loggedOut* 。若交叉命中→据此收紧 platforms.js 的选择器。");
  }
})();
