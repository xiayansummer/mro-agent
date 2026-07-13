import { test } from "node:test";
import assert from "node:assert/strict";
import { detailToString } from "./api.js";

test("detailToString 字符串 detail 原样返回", () => {
  assert.equal(detailToString("扩展未绑定或已失效"), "扩展未绑定或已失效");
});

test("detailToString FastAPI 422 对象数组取 msg 拼接(修 [object Object])", () => {
  // 真实触发场景:新扩展向旧后端上报 platform="1688",Pydantic Literal 校验失败返回此结构。
  const detail = [
    { loc: ["body", "platforms", 3, "platform"], msg: "Input should be 'jd', 'zkh' or 'ehsy'", type: "literal_error" },
    { loc: ["body", "platforms", 3, "platform"], msg: "字段必填", type: "missing" },
  ];
  assert.equal(detailToString(detail), "Input should be 'jd', 'zkh' or 'ehsy'；字段必填");
});

test("detailToString 单对象取 msg,无 msg 兜底 JSON", () => {
  assert.equal(detailToString({ msg: "校验失败" }), "校验失败");
  assert.equal(detailToString({ code: 42 }), '{"code":42}');
});

test("detailToString 空值返回空串", () => {
  assert.equal(detailToString(null), "");
  assert.equal(detailToString(undefined), "");
});
