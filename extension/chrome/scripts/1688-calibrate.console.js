// 1688 搜索结果页解析校准脚本。
// 用法:在真实 1688 搜索结果页(s.1688.com/selloffer/offer_search.htm?keywords=...)的 DevTools
// Console 里粘贴运行。它用与 alibaba1688Parser.js 相同的结构启发式,打印命中的商品卡片数 +
// 前 5 条提取结果(标题/价格/图/链接),人工核对;不对就据页面真实结构调 parser 的正则/规则。
//
// ⚠️ 1688 列表页 class 全混淆、无 data-*,故靠 href 锚定卡片 + 文本模式,不靠 class(见 parser 注释)。
(() => {
  const OFFER_HREF_RE = /detail\.1688\.com|dj\.1688\.com|1688\.com\/offer\/|\/\d{9,}\.html/i;
  const PRICE_RE = /(?:¥|￥)\s*([\d.]+)(?:\s*[-~至]\s*([\d.]+))?/;
  const MOQ_RE = /(\d+)\s*(件|个|套|米|千克|kg|双|只|条|包|箱|卷|张)\s*起(?:批|订|拍)?/;

  const cards = [...document.querySelectorAll("a[href]")].filter(
    (a) => OFFER_HREF_RE.test(a.href) && a.querySelector("img"),
  );
  console.log(
    "%c命中商品卡片数: " + cards.length,
    "font-weight:bold",
    "(应与页面商品数接近;偏少→OFFER_HREF_RE 要补新的详情 URL 模式,偏多→广告未滤干净)",
  );
  cards.slice(0, 5).forEach((c, i) => {
    const leaf = [...c.querySelectorAll("*")].filter((e) => !e.children.length && (e.textContent || "").trim());
    const title = leaf
      .map((e) => e.textContent.trim())
      .filter((t) => /[一-龥]/.test(t) && t.length > 4 && !/^广告$|^立即查看$/.test(t))
      .sort((a, b) => b.length - a.length)[0];
    console.log(`#${i}`, {
      title,
      price: (c.textContent.match(PRICE_RE) || [])[0] || "(未匹配)",
      moq: (c.textContent.match(MOQ_RE) || [])[0] || "(列表页无,正常)",
      img: (c.querySelector("img")?.src || "").slice(0, 55),
      href: (c.href || "").slice(0, 65),
    });
  });
  console.log("核对:title/price/img 对不对?price 是起批价(非批发底价)。若字段错位,把某张卡片 outerHTML 发我调规则。");
})();
