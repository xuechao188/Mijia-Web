/* 设备类型图标回归（Node 直接跑，无 DOM 依赖）。 */
"use strict";
const I = require("../static/device_icons.js");
const C = require("../static/cards.js");

let n = 0;
function ok(cond, msg) {
  if (!cond) throw new Error(msg);
  n++;
}

// 14 个类别与 cards.js 的 CATEGORY_LABELS 必须一一对应，
// 少一个就意味着某类设备会掉到通用立方体图标上。
const cats = Object.keys(C.CATEGORY_LABELS);
ok(I.CATS.length === 14, "图标覆盖 14 个类别");
for (const c of cats) {
  ok(I.has(c), "类别 " + c + " 有专属图标");
}

// 外壳统一：viewBox / 无填充 / 取 currentColor（颜色交给 CSS 的 --cat）
const svg = I.svg("light");
ok(svg.indexOf('viewBox="0 0 24 24"') >= 0, "统一 24×24 视框");
ok(svg.indexOf('stroke="currentColor"') >= 0, "描边取 currentColor");
ok(svg.indexOf('fill="none"') >= 0, "不填充，避免开着时反白变实心块");
ok(svg.indexOf("<path") >= 0 || svg.indexOf("<circle") >= 0, "图标含实际图形");
ok(svg.indexOf("<svg") === 0 && svg.indexOf("</svg>") === svg.length - 6,
   "返回完整 svg 片段（可直接塞 innerHTML）");

// 每一类都能生成、且互不相同（防止复制粘贴时漏改）
const seen = {};
for (const c of I.CATS) {
  const s = I.svg(c);
  ok(s.length > 80, "类别 " + c + " 图标非空");
  ok(!seen[s], "类别 " + c + " 的图标与他人重复");
  seen[s] = c;
}

// 未知类别回退通用图标，不抛错、不返回空串
ok(I.svg("not-a-category") === I.svg("generic"), "未知类别回退通用立方体");
ok(I.svg(undefined) === I.svg("generic"), "缺参回退通用立方体");
ok(!I.has("not-a-category"), "has() 对未知类别返回 false");

console.log("device_icons 测试通过：%d 项", n);
