/* ④ 天气卡片回归：纯函数 + DOM 桩渲染（Node 直接跑，无需浏览器）。 */
"use strict";
const W = require("../static/weather_card.js");
const T = require("../static/card_types.js");

let n = 0;
function ok(cond, msg) {
  if (!cond) throw new Error(msg);
  n++;
}

// ---------------------------------------------------------------- 纯函数
ok(W.kindOf(0) === "sun" && W.kindOf(1) === "sun", "晴 / 大部晴朗");
ok(W.kindOf(2) === "partly" && W.kindOf(3) === "cloud", "多云 / 阴");
ok(W.kindOf(45) === "fog" && W.kindOf(48) === "fog", "雾");
ok([51, 61, 65, 80, 82].every((c) => W.kindOf(c) === "rain"), "各类降雨");
ok([71, 75, 85, 86].every((c) => W.kindOf(c) === "snow"), "各类降雪");
ok([95, 96, 99].every((c) => W.kindOf(c) === "storm"), "雷暴");
ok(W.kindOf(12345) === "cloud", "未知天气码回退云");
ok(W.iconSvg("rain", 32).indexOf('width="32"') >= 0, "图标尺寸可指定");
ok(W.iconSvg("rain").indexOf("<svg") === 0, "图标是内联 SVG（不依赖图片资源）");
ok(W.iconSvg("nope").indexOf("<svg") === 0, "未知图标种类有兜底");

ok(W.aqiGrade(null).label === "--", "AQI 无数据显示占位");
ok(W.aqiGrade(undefined).level === 0, "AQI 未定义不报错");
ok(W.aqiGrade(12).label === "优", "欧标 AQI 优");
ok(W.aqiGrade(35).text === "AQI 35 · 良", "欧标 AQI 良含数值");
ok(W.aqiGrade(55).label === "中等", "欧标 AQI 中等");
ok(W.aqiGrade(101).label === "很差", "欧标 AQI 超出分档");
ok(W.aqiGrade("abc").level === 0, "非数值 AQI 不误判");

ok(W.fieldsFor("sm").length === 2, "小卡只显示 2 类信息");
ok(W.fieldsFor("md").indexOf("aqi") >= 0, "中卡含空气质量");
ok(W.fieldsFor("md").indexOf("hourly") < 0, "中卡不画曲线");
ok(W.fieldsFor("lg").indexOf("hourly") >= 0, "大卡画 24 小时曲线");
ok(W.fieldsFor("xx").join() === W.fieldsFor("md").join(), "未知尺寸回退中卡");
const copy = W.fieldsFor("sm"); copy.push("hack");
ok(W.fieldsFor("sm").length === 2, "字段表返回副本，外部改不动");

ok(W.tempText(18.6) === "19", "温度默认取整");
ok(W.tempText(18.64, 1) === "18.6", "温度可指定小数位");
ok(W.tempText(null) === "--" && W.tempText("x") === "--", "异常温度显示占位");
ok(W.tempText(0) === "0", "零度不被当成空值");
ok(W.pctText(63.7) === "64%" && W.pctText(null) === "--", "百分比格式化");

const w = {
  city: "合肥", temp: 18.4, feels: 17, code: 2, text: "多云", wind: 9,
  humidity: 63, aqi: 35, is_day: 1, updated: "10:45", stale: false,
  today: { tmax: 21, tmin: 11, pop_max: 30, sunrise: "06:32", sunset: "17:20" },
  hourly: [
    { time: "10:00", temp: 18, pop: 0 },
    { time: "11:00", temp: 20, pop: 10 },
    { time: "12:00", temp: null, pop: 20 },
    { time: "13:00", temp: 22, pop: 30 },
  ],
};
ok(W.hourlySeries(w).length === 3, "曲线跳过空温点");
ok(JSON.stringify(W.hourlySeries(w)[0]) === "[0,18]", "曲线点为 [序号, 温度]");
ok(JSON.stringify(W.tempRange(w)) === '{"min":18,"max":22}', "曲线最高最低温");
ok(JSON.stringify(W.hourlyLabels(w)) === '["10:00","13:00"]', "曲线首尾时间标签");
ok(W.hourlySeries({}).length === 0, "无逐时数据不崩");
ok(JSON.stringify(W.tempRange({})) === '{"min":null,"max":null}', "无数据温度范围为空");

// ---------------------------------------------------------------- DOM 桩
function El(tag) {
  const e = {
    tag, className: "", children: [], dataset: {}, listeners: {},
    _html: "", value: "", title: "", textContent: "",
    appendChild(c) { this.children.push(c); c.parentNode = this; return c; },
    addEventListener(t, f) { this.listeners[t] = f; },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = v; this.children = []; },
    get classList() {
      const self = this;
      return { add(...cs) { cs.forEach((c) => { if (!self.className.split(" ").includes(c)) self.className += " " + c; }); },
               remove(...cs) { self.className = self.className.split(" ").filter((c) => !cs.includes(c)).join(" "); } };
    },
  };
  return e;
}
function findAll(node, cls) {
  const out = [];
  (function walk(x) {
    for (const c of x.children || []) {
      if ((c.className || "").split(/\s+/).indexOf(cls) >= 0) out.push(c);
      walk(c);
    }
  })(node);
  return out;
}
const doc = { createElement: (t) => El(t) };
const calls = { size: [], open: 0, city: [] };
const handlers = {
  doc,
  sparkline: (pts, opt) => T.sparkline(pts, opt),
  onSize: (s) => calls.size.push(s),
  onOpen: () => { calls.open++; },
  onCity: (c) => calls.city.push(c),
};

// ---------------------------------------------------------------- 卡片渲染
const sm = W.render(w, "sm", handlers);
ok(sm.className.indexOf("device-card weather-card sz-sm") >= 0, "天气卡沿用设备卡基类与尺寸类");
ok(sm.className.indexOf("wc-partly") >= 0, "按天气码加视觉主题");
ok(sm.dataset.widget === "weather", "标记为天气挂件，便于轮询时区分设备");
ok(findAll(sm, "wc-temp")[0].textContent === "18°", "小卡显示温度");
ok(findAll(sm, "wc-metrics").length === 0, "小卡不铺读数网格");
ok(findAll(sm, "wc-chart").length === 0, "小卡不画曲线");
ok(findAll(sm, "wc-tag").length === 0, "小卡不显示标签，避免拥挤");
ok(findAll(sm, "wc-size").length === 3, "卡片上可切换三尺寸");

const md = W.render(w, "md", handlers);
ok(md.className.indexOf("sz-md") >= 0, "中卡带尺寸类");
ok(findAll(md, "wc-metric").length === 4, "中卡 4 项读数（体感/今日/空气/风速）");
ok(findAll(md, "wc-chart").length === 0, "中卡不画曲线");
ok(findAll(md, "wc-tag").length === 1, "中卡显示天气标签");

const lg = W.render(w, "lg", handlers);
ok(lg.className.indexOf("sz-lg") >= 0, "大卡带尺寸类");
ok(findAll(lg, "wc-metric").length === 7, "大卡 7 项读数");
ok(findAll(lg, "wc-chart").length === 1, "大卡画 24 小时曲线");
ok((findAll(lg, "ct-chart-svg")[0].innerHTML || "").indexOf("<polyline") >= 0,
   "大卡曲线内嵌 SVG 折线");
ok(findAll(lg, "wc-foot")[0].children[0].textContent === "更新于 10:45", "卡片标注更新时间");

findAll(lg, "wc-size")[2].onclick({ stopPropagation() {} });
ok(calls.size[calls.size.length - 1] === "lg", "点击尺寸按钮回调带上目标尺寸");
lg.onclick();
ok(calls.open === 1, "点击卡片打开详情");

const stale = Object.assign({}, w, { stale: true });
ok(findAll(W.render(stale, "md", handlers), "wc-foot")[0].children[0].textContent
   === "数据未更新", "接口失败回退旧数据时明确标注");

const empty = W.render({ code: 3, temp: null }, "lg", handlers);
ok(findAll(empty, "ct-chart-empty").length === 1, "无逐时数据时给出提示而非空白");

// ---------------------------------------------------------------- 抽屉渲染
const dr = W.drawer(w, "md", handlers);
ok(findAll(dr, "wc-hero-temp")[0].textContent === "18°", "抽屉主温度");
ok(findAll(dr, "dr-readout").length === 8, "抽屉列出 8 项完整读数");
ok(findAll(dr, "wc-chart").length === 1, "抽屉有完整温度曲线");
ok(findAll(dr, "wc-hours")[0].children.length === 2, "逐小时列表按每 3 小时抽样");
ok(findAll(dr, "wc-size").length === 3, "抽屉可切尺寸");
ok(findAll(dr, "wc-note").length === 1, "抽屉注明数据来源与 AQI 标准");

const cityInput = findAll(dr, "text-input")[0];
cityInput.value = "  北京  ";
const buttons = findAll(dr, "toggle-btn");
buttons[0].onclick();
ok(calls.city[0] === "北京", "保存城市时去除首尾空格");
buttons[1].onclick();
ok(calls.city[1] === "", "恢复默认城市传空串");

// ---------------------------------------------------------------- 断网降级
const unavailable = { city: "合肥", unavailable: true, text: "天气暂不可用", code: 3 };
const ue = W.render(unavailable, "lg", handlers);
ok(ue.className.indexOf("sz-lg") >= 0, "天气不可用时仍保留所选尺寸");
ok(ue.className.indexOf("weather-card") >= 0, "天气不可用时卡片骨架不消失");
ok(findAll(ue, "wc-temp")[0].textContent === "--°", "温度显示占位符");
ok(findAll(ue, "wc-metrics").length === 0, "不可用时不铺一排空读数");
ok(findAll(ue, "wc-chart").length === 0, "不可用时不画空曲线");
ok(findAll(ue, "wc-tag")[0].textContent === "暂不可用", "标签标明暂不可用");
ok(findAll(ue, "wc-foot")[0].children[0].textContent.indexOf("天气暂不可用") >= 0,
   "卡片提示稍后自动重试");

handlers.onRetry = () => { calls.retry = (calls.retry || 0) + 1; };
const dr2 = W.drawer(w, "md", handlers);
const buttons2 = findAll(dr2, "toggle-btn");
ok(buttons2.length === 3, "抽屉提供保存 / 恢复默认 / 刷新天气");
buttons2[2].onclick();
ok(calls.retry === 1, "刷新天气触发重新拉取");

console.log("weather_card_test: " + n + " 项通过");
