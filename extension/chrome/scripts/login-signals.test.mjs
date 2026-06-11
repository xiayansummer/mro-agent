import { test } from "node:test";
import assert from "node:assert/strict";

import { interpretLoginSignals, isCacheFresh } from "../src/loginProbe.js";

const TTL = 30 * 60 * 1000; // 与 LOGIN_PROBE_TTL_MINUTES 对齐

test("登录态缓存:TTL 内视为新鲜 → 心跳复用、不再打开平台页(避免风控)", () => {
  const now = 1_000_000_000_000;
  assert.equal(isCacheFresh(now - 60 * 1000, now, TTL), true); // 1 分钟前探的,仍新鲜
});

test("登录态缓存:超过 TTL → 需重新探测", () => {
  const now = 1_000_000_000_000;
  assert.equal(isCacheFresh(now - 31 * 60 * 1000, now, TTL), false); // 31 分钟前,过期
});

test("登录态缓存:无时间戳(从未探过)→ 不新鲜,需探测", () => {
  assert.equal(isCacheFresh(undefined, 1_000_000_000_000, TTL), false);
});

test("明确已登录特征 → loggedIn true", () => {
  assert.deepEqual(
    interpretLoginSignals({ loggedInSignals: 2, loggedOutSignals: 0 }),
    { loggedIn: true, message: "检测到已登录特征" },
  );
});

test("登录与未登录信号并存(登录页常残留入口),登录信号占优 → true", () => {
  assert.equal(interpretLoginSignals({ loggedInSignals: 1, loggedOutSignals: 1 }).loggedIn, true);
});

test("仅检测到未登录入口 → loggedIn false", () => {
  assert.equal(interpretLoginSignals({ loggedInSignals: 0, loggedOutSignals: 1 }).loggedIn, false);
});

test("无任何特征(SPA 还没渲染)→ loggedIn null(无法判断,不误判未登录)", () => {
  assert.equal(interpretLoginSignals({ loggedInSignals: 0, loggedOutSignals: 0 }).loggedIn, null);
});

test("信号矛盾、未登录略占优 → null(不轻易判未登录)", () => {
  assert.equal(interpretLoginSignals({ loggedInSignals: 1, loggedOutSignals: 2 }).loggedIn, null);
});
