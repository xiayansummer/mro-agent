import { test } from "node:test";
import assert from "node:assert/strict";

import {
  isZkhSearchResultUrl,
  isOrderCodePlaceholder,
  classifyZkhPage,
} from "../src/zkhParser.js";

// ---- isZkhSearchResultUrl:收紧"真实搜索结果页"的 URL 判定 ----
test("isZkhSearchResultUrl: 带 keywords 的搜索结果页 → true", () => {
  assert.equal(
    isZkhSearchResultUrl("https://www.zkh.com/search.html?keywords=%E7%BE%8E%E5%92%8C%20%E6%89%8B%E6%8B%89%E8%91%AB%E8%8A%A6"),
    true,
  );
});

test("isZkhSearchResultUrl: 登录页 → false", () => {
  assert.equal(isZkhSearchResultUrl("https://www.zkh.com/login"), false);
});

test("isZkhSearchResultUrl: 首页 → false", () => {
  assert.equal(isZkhSearchResultUrl("https://www.zkh.com/"), false);
});

test("isZkhSearchResultUrl: search 路径但无 keyword 参数 → false", () => {
  assert.equal(isZkhSearchResultUrl("https://www.zkh.com/search.html"), false);
});

test("isZkhSearchResultUrl: 非 zkh 域 → false", () => {
  assert.equal(isZkhSearchResultUrl("https://evil.com/search.html?keywords=x"), false);
});

test("isZkhSearchResultUrl: passport 子域登录页(即便 redirect 里含 keywords)→ false", () => {
  assert.equal(
    isZkhSearchResultUrl("https://passport.zkh.com/login?redirect=%2Fsearch.html%3Fkeywords%3Dx"),
    false,
  );
});

// ---- isOrderCodePlaceholder:识别"订货编码"占位标题(非真实商品名)----
test("isOrderCodePlaceholder: 全角冒号订货编码 → true", () => {
  assert.equal(isOrderCodePlaceholder("订货编码：AE4559028"), true);
});

test("isOrderCodePlaceholder: 半角冒号订货编码 → true", () => {
  assert.equal(isOrderCodePlaceholder("订货编码:AE2910560"), true);
});

test("isOrderCodePlaceholder: 裸编码 AE+数字 → true", () => {
  assert.equal(isOrderCodePlaceholder("AE4559028"), true);
});

test("isOrderCodePlaceholder: 正常商品标题 → false", () => {
  assert.equal(isOrderCodePlaceholder("美和TOHO 手拉葫芦1吨6米手动吊机起重三角葫芦"), false);
});

test("isOrderCodePlaceholder: 杂牌但正常的标题 → false", () => {
  assert.equal(isOrderCodePlaceholder("沪工手拉葫芦1吨吊葫芦2吨3吨环链起重"), false);
});

// ---- classifyZkhPage:综合信号 → 'results' | 'login_required' | 'empty' ----
test("classifyZkhPage: 真实结果页且有有效商品 → results", () => {
  assert.equal(
    classifyZkhPage({ isSearchUrl: true, validOfferCount: 5, hasLoginWall: false, hasPriceSignal: true }),
    "results",
  );
});

test("classifyZkhPage: 被重定向走(非搜索 URL)→ login_required", () => {
  assert.equal(
    classifyZkhPage({ isSearchUrl: false, validOfferCount: 0, hasLoginWall: false, hasPriceSignal: false }),
    "login_required",
  );
});

test("classifyZkhPage: 搜索 URL 但有登录墙且无有效商品 → login_required", () => {
  assert.equal(
    classifyZkhPage({ isSearchUrl: true, validOfferCount: 0, hasLoginWall: true, hasPriceSignal: false }),
    "login_required",
  );
});

test("classifyZkhPage: 真实搜索页、无登录墙、但无匹配商品 → empty", () => {
  assert.equal(
    classifyZkhPage({ isSearchUrl: true, validOfferCount: 0, hasLoginWall: false, hasPriceSignal: true }),
    "empty",
  );
});

test("classifyZkhPage: 搜索页无有效商品、无价格信号、无明显登录墙 → login_required(疑似默认/拦截页)", () => {
  // 对应线上证据:未登录默认页解析不出真实商品、也没有价格语义
  assert.equal(
    classifyZkhPage({ isSearchUrl: true, validOfferCount: 0, hasLoginWall: false, hasPriceSignal: false }),
    "login_required",
  );
});
