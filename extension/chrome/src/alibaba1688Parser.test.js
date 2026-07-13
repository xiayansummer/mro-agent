import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parsePrice,
  parseMoq,
  classify1688Page,
  extractTitle,
  extractPriceText,
} from "./alibaba1688Parser.js";

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

// 真实卡片叶子节点顺序(2026-07-13 浏览器实测):标题在前、属性、价格拆成 ¥|0|.05、再销量/物流。
const REAL_CARD_LEAVES = [
  "304不锈钢内六角螺丝圆柱杯头内六角螺栓滚花螺钉M2-M6",
  "6mm",
  "｜",
  "304不锈钢",
  "｜",
  "DIN912",
  "¥",
  "0",
  ".05",
  "全网10万+件",
  "退货包运费",
  "明天达",
];

test("extractTitle 取价格节点前的非噪声叶子,结构性排除尾部成交计数", () => {
  const t = extractTitle(REAL_CARD_LEAVES);
  assert.ok(t.startsWith("304不锈钢内六角螺丝"), t);
  assert.ok(!t.includes("全网"), "标题不应含价格后的成交计数");
  assert.ok(!/10万\+件/.test(t), "标题不应含成交计数");
});

test("extractTitle 合并被拆分的纯中文碎片(六角+螺栓→六角螺栓)", () => {
  assert.equal(extractTitle(["六角", "螺栓", "¥", "2", ".3", "退货包运费"]), "六角螺栓");
});

test("extractTitle 保留规格段、剔除促销/公司名/分隔符", () => {
  const leaves = ["外六角螺栓", "10B21(碳钢)", "｜", "发黑", "｜", "8.8级", "¥", "0", ".1", "10万+件", "河北圣衍金属制品有限公司"];
  assert.equal(extractTitle(leaves), "外六角螺栓 10B21(碳钢) 发黑 8.8级");
});

test("extractTitle 促销标签在价格前也被剔除,只取真实标题", () => {
  assert.equal(extractTitle(["外六角螺栓", "好评率100%的口碑商品", "¥", "0", ".25", "1500+件"]), "外六角螺栓");
});

test("extractTitle 无价格节点时跳过公司名/促销,取商品标题", () => {
  const leaves = ["临沂泰克普路机械有限公司", "全网10万+件", "热镀锌外六角螺栓光伏螺丝M8*20"];
  assert.equal(extractTitle(leaves), "热镀锌外六角螺栓光伏螺丝M8*20");
});

test("extractPriceText 拼接拆分的 ¥/整数/小数 节点,遇销量即停(不粘连)", () => {
  // 关键回归:整卡 textContent 会得到 "¥0.05全网10万+件" → 误解析成 "¥0.0510";
  // 逐节点拼接必须在 "全网10万+件" 处停,只保留 "¥0.05"。
  assert.equal(extractPriceText(REAL_CARD_LEAVES), "¥0.05");
  assert.deepEqual(parsePrice(extractPriceText(REAL_CARD_LEAVES)), {
    priceValue: 0.05,
    priceText: "¥0.05",
  });
});

test("extractPriceText 价格在单节点/无价格", () => {
  assert.equal(extractPriceText(["热镀锌螺栓", "¥1.2", "起批"]), "¥1.2");
  assert.equal(extractPriceText(["面议", "供应"]), "");
});

test("classify1688Page 登录墙/空/正常", () => {
  assert.equal(classify1688Page({ isSearchUrl: true, validOfferCount: 5, hasLoginWall: false }), "ok");
  assert.equal(classify1688Page({ isSearchUrl: true, validOfferCount: 0, hasLoginWall: true }), "login_required");
  assert.equal(classify1688Page({ isSearchUrl: true, validOfferCount: 0, hasLoginWall: false }), "empty");
});
