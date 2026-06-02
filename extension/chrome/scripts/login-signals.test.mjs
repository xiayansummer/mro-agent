import { test } from "node:test";
import assert from "node:assert/strict";

import { interpretLoginSignals } from "../src/loginProbe.js";

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
