export const PLATFORMS = [
  {
    id: "jd",
    label: "京东工业品",
    probeUrl: "https://mro.jd.com/",
    loginUrl: "https://passport.jd.com/new/login.aspx",
    loggedInSelectors: [
      ".nickname",
      ".user-name",
      ".account",
      "[class*='user'] [class*='name']",
    ],
    loggedOutSelectors: [
      "a[href*='passport.jd.com']",
      "a[href*='login']",
      ".login",
      "[class*='login']",
    ],
    loggedInText: [
      "退出",
      "我的京东",
      "账户中心",
    ],
    loggedOutText: [
      "请登录",
      "登录",
      "免费注册",
    ],
  },
  {
    id: "zkh",
    label: "震坤行",
    probeUrl: "https://www.zkh.com/",
    loginUrl: "https://www.zkh.com/login",
    // ⚠️ 以下登录态特征需用真实震坤行登录/未登录页校准
    // (见 scripts/zkh-calibrate.console.js)。震坤行是 SPA,配合 loginProbe
    // 的页面内轮询等待一起使用。
    loggedInSelectors: [
      ".user-name",
      ".nickname",
      ".account",
      "[class*='user'] [class*='name']",
      "[class*='member']",
      "[class*='avatar']",
    ],
    loggedInText: [
      "退出登录",
      "我的震坤行",
      "账户中心",
      "我的订单",
    ],
    // 收紧到明确的登录入口:去掉过宽的 .login / [class*='login'],
    // 它们在登录后页面仍可能命中,导致"已登录被判未登录"。
    loggedOutSelectors: [
      "a[href*='/login']",
      "a[href*='passport.zkh']",
    ],
    // ⚠️ 不要用裸"登录"——已登录页的"退出登录"也含该词,会误判未登录。
    loggedOutText: [
      "请登录",
      "登录/注册",
      "立即登录",
      "您还未登录",
    ],
  },
];

export function getPlatform(platformId) {
  return PLATFORMS.find((platform) => platform.id === platformId);
}
