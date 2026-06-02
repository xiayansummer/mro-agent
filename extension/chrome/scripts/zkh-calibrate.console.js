// ============================================================
// 震坤行登录态 / 搜索结果页 —— 人工校准片段(不参与扩展运行)
//
// 背景:loginProbe.js(登录探测)和 zkhParser.js(结果页/登录墙识别)里
// 的选择器与短语,需要用真实震坤行页面校准。把本片段复制到 Chrome
// DevTools 控制台运行,会打印当前页面命中了哪些登录/未登录特征。
//
// 建议在 4 种场景各跑一次,把输出回贴,据此回填:
//   1) 已登录 - 首页           https://www.zkh.com/
//   2) 未登录 - 首页(无痕窗口)
//   3) 已登录 - 搜索结果页      https://www.zkh.com/search.html?keywords=手拉葫芦
//   4) 未登录 - 同一搜索页(无痕窗口)
//
// 校准目标:
//   - 已登录场景:loggedInSignals 应 ≥ 1(否则补强 loggedInSelectors/Text)
//   - 未登录场景:loggedOutSignals 应 ≥ 1 且 loggedInSignals = 0
//   - 未登录搜索页:loginWallHit 应为 true 或 hasPriceSignal 为 false
//     (这样 classifyZkhPage 才会判 login_required,而不是把默认页当结果)
// ============================================================
(() => {
  const text = document.body?.innerText || "";

  // —— 下列四组需与 extension/chrome/src/platforms.js 的 zkh 配置保持一致 ——
  const loggedInSelectors = [
    ".user-name", ".nickname", ".account",
    "[class*='user'] [class*='name']", "[class*='member']", "[class*='avatar']",
  ];
  const loggedInText = ["退出登录", "我的震坤行", "账户中心", "我的订单"];
  const loggedOutSelectors = ["a[href*='/login']", "a[href*='passport.zkh']"];
  const loggedOutText = ["请登录", "登录/注册", "立即登录", "您还未登录"];
  // 与 zkhParser.js 的 detectLoginWall 保持一致
  const loginWall = /请登录|登录后查看|登录查看|您(还|尚)未登录|未登录|立即登录|登录\/注册/;

  const hitSel = (list) => list.filter((s) => { try { return document.querySelector(s); } catch { return false; } });
  const hitTxt = (list) => list.filter((t) => text.includes(t));

  const params = new URLSearchParams(location.search);
  const isSearchResultUrl =
    /(^|\.)zkh\.com$/i.test(location.hostname)
    && !/passport\.zkh\.com$/i.test(location.hostname)
    && /search/i.test(location.pathname)
    && (params.has("keywords") || params.has("keyword"));

  const loggedInSelHit = hitSel(loggedInSelectors);
  const loggedInTxtHit = hitTxt(loggedInText);
  const loggedOutSelHit = hitSel(loggedOutSelectors);
  const loggedOutTxtHit = hitTxt(loggedOutText);

  const report = {
    url: location.href,
    isSearchResultUrl,
    hasPriceSignal: /[¥￥]/.test(text),
    loginWallHit: loginWall.test(text),
    productCardCount: document.querySelectorAll(
      "[class*='goods'],[class*='product'],[class*='item'],[class*='sku'],[class*='commodity']",
    ).length,
    loggedIn: { selectorsHit: loggedInSelHit, textHit: loggedInTxtHit },
    loggedOut: { selectorsHit: loggedOutSelHit, textHit: loggedOutTxtHit },
    loggedInSignals: (loggedInSelHit.length ? 1 : 0) + (loggedInTxtHit.length ? 1 : 0),
    loggedOutSignals: (loggedOutSelHit.length ? 1 : 0) + (loggedOutTxtHit.length ? 1 : 0),
  };

  console.log("=== 震坤行校准报告（把整段输出回贴给我）===");
  console.log(JSON.stringify(report, null, 2));
  return report;
})();
