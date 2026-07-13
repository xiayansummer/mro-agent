import { test } from "node:test";
import assert from "node:assert/strict";
import { parsePrice, parseMoq, classify1688Page } from "./alibaba1688Parser.js";

test("parsePrice 起批单价(真实页全角￥+空格格式,规范化输出)", () => {
  assert.deepEqual(parsePrice("￥ 0.25"), { priceValue: 0.25, priceText: "¥0.25" });
  assert.deepEqual(parsePrice("￥ 1.2"), { priceValue: 1.2, priceText: "¥1.2" });
});

test("parsePrice 区间取下限", () => {
  assert.deepEqual(parsePrice("¥2.5-3.0"), { priceValue: 2.5, priceText: "¥2.5-3.0" });
});

test("parsePrice 无价格返回 null", () => {
  assert.equal(parsePrice("面议").priceValue, null);
});

test("parseMoq 有则取、无则空", () => {
  assert.equal(parseMoq("100件起批"), "≥100件");
  assert.equal(parseMoq("2个起订"), "≥2个");
  assert.equal(parseMoq("现货充足"), "");
});

test("classify1688Page 登录墙/空/正常", () => {
  assert.equal(classify1688Page({ isSearchUrl: true, validOfferCount: 5, hasLoginWall: false }), "ok");
  assert.equal(classify1688Page({ isSearchUrl: true, validOfferCount: 0, hasLoginWall: true }), "login_required");
  assert.equal(classify1688Page({ isSearchUrl: true, validOfferCount: 0, hasLoginWall: false }), "empty");
});
