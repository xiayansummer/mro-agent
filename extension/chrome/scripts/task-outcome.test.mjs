import { test } from "node:test";
import assert from "node:assert/strict";

import { decideSubtaskOutcome } from "../src/taskOutcome.js";

test("有有效 offers → done", () => {
  const o = decideSubtaskOutcome({ offers: [{ title: "美和TOHO 手拉葫芦1吨6米" }], searchTerm: "t" });
  assert.equal(o.status, "done");
});

test("无 offers + loginRequired → login_required,message 含登录态标记", () => {
  const o = decideSubtaskOutcome({ offers: [], error: "震坤行登录态未知", loginRequired: true });
  assert.equal(o.status, "login_required");
  assert.match(o.message, /登录态未知|平台未登录|login_required/);
});

test("无 offers + 普通 error → failed,透传原始 error", () => {
  const o = decideSubtaskOutcome({ offers: [], error: "未解析到搜索结果" });
  assert.equal(o.status, "failed");
  assert.equal(o.message, "未解析到搜索结果");
});

test("无 offers + loginRequired 但无 error → login_required,有兜底登录提示", () => {
  const o = decideSubtaskOutcome({ offers: [], loginRequired: true });
  assert.equal(o.status, "login_required");
  assert.match(o.message, /登录/);
});

test("loginRequired 但仍拿到 offers → done(有真实结果优先)", () => {
  const o = decideSubtaskOutcome({ offers: [{ title: "x" }], loginRequired: true });
  assert.equal(o.status, "done");
});

test("offers 字段缺失(undefined)按空处理 → failed", () => {
  const o = decideSubtaskOutcome({ error: "boom" });
  assert.equal(o.status, "failed");
});

test("既无 offers 也无 error 也无 loginRequired → failed(兜底)", () => {
  const o = decideSubtaskOutcome({ offers: [] });
  assert.equal(o.status, "failed");
});
