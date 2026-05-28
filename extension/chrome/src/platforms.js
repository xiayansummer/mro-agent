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
    loggedInSelectors: [
      ".user-name",
      ".nickname",
      ".account",
      "[class*='user'] [class*='name']",
    ],
    loggedOutSelectors: [
      "a[href*='login']",
      ".login",
      "[class*='login']",
    ],
    loggedInText: [
      "退出",
      "我的震坤行",
      "账户中心",
    ],
    loggedOutText: [
      "登录",
      "注册",
    ],
  },
];

export function getPlatform(platformId) {
  return PLATFORMS.find((platform) => platform.id === platformId);
}
