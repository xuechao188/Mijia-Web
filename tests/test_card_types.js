/* ③ 分类卡片纯函数回归（Node 直接跑，无 DOM 依赖）。 */
"use strict";
const C = require("../static/cards.js");
const T = require("../static/card_types.js");

let n = 0;
function ok(cond, msg) {
  if (!cond) throw new Error(msg);
  n++;
}
function dev(extra) {
  return Object.assign({ did: "d", name: "n", model: "x.y.z", product: "",
                        online: true }, extra || {});
}
function ctrl(key, extra) {
  return Object.assign({ key, kind: "range", label: key, unit: "",
                         min: 1, max: 100, step: 1, siid: 2, piid: 3,
                         writable: true, readable: true }, extra || {});
}

// ---------------------------------------------------------------- 读数本地化
ok(T.labelOf("temperature") === "温度", "读数键中文名");
ok(T.labelOf("unknown-key") === "unknown-key", "未知读数键原样回退");
ok(T.formatValue("temperature", 18.14) === "18.1°C", "温度按 1 位小数带单位");
ok(T.formatValue("humidity", 63.7) === "64%", "湿度取整带百分号");
ok(T.formatValue("voltage", 220.123) === "220.1V", "电压带单位");
ok(T.formatValue("motion", true) === "有人", "布尔读数转中文状态");
ok(T.formatValue("contact", false) === "闭合", "门磁布尔读数");
ok(T.formatValue("temperature", null) === "", "空读数不显示");
ok(T.formatValue("temperature", undefined) === "", "未定义读数不显示");
ok(T.formatValue("temperature", 0) === "0°C", "零值不被过滤");
ok(T.formatValue("temperature", NaN) === "NaN", "非有限值不当成数字格式化");
ok(T.formatValue("humidity", 50, dev({ readable: { humidity: { unit: "percentage" } } })) === "50%",
   "spec 单位映射");
ok(T.formatValue("brightness", 60, dev({ controls: [ctrl("brightness", { unit: "%" })] })) === "60%",
   "控件单位回退");

// ---------------------------------------------------------------- 产品名 / 开关名
ok(T.productLabel(dev({ product: "Light" })) === "智能灯", "英文产品名翻译");
ok(T.productLabel(dev({ product: "Three Key Switch" })) === "三键开关", "多键开关产品名翻译");
ok(T.productLabel(dev({ product: "Water Purifier" })) === "净水器", "净水器产品名翻译");
ok(T.productLabel(dev({ product: "xiaomi fryer st701" })) === "空气炸锅", "厨电产品名翻译");
ok(T.productLabel(dev({ product: "温湿度传感器" })) === "温湿度计", "中文产品名保留规则");
ok(T.productLabel(dev({ product: "lumi.ctrl_neutral2.v1" })) === "", "纯型号不冒充产品名");
ok(T.switchLabel({ label: "Left Switch Service" }, 0) === "左键", "左键标签");
ok(T.switchLabel({ label: "Middle Switch Service" }, 1) === "中键", "中键标签");
ok(T.switchLabel({ label: "Right Switch Service" }, 2) === "右键", "右键标签");
ok(T.switchLabel({ label: "switch-toggle" }, 3) === "切换", "第四路切换标签");
ok(T.switchLabel({ label: "on2" }, 1) === "按键 2", "占位标签按序编号");

// ---------------------------------------------------------------- 控件筛选
ok(T.pickControl(dev({ controls: [ctrl("brightness"), ctrl("mode")] }), "brightness").min === 1,
   "按 key 取控件");
ok(T.pickControl(dev({}), "brightness") === null, "缺控件返回 null");
const lamp = dev({ model: "philips.light.sread9",
  controls: [ctrl("brightness"), ctrl("color-temperature", { min: 2700, max: 5500 })] });
ok(T.cardControls(lamp, "light", "sm").length === 0, "小卡不放滑杆");
ok(T.cardControls(lamp, "light", "md").length === 1, "中卡只放亮度滑杆");
ok(T.cardControls(lamp, "light", "lg").length === 2, "大卡放亮度 + 色温");
ok(T.cardControls(dev({ controls: [ctrl("mode")] }), "light", "lg").length === 0,
   "不支持亮度/色温的灯不出现滑杆");
const fryer = dev({ controls: [ctrl("target-temperature", { min: 30, max: 230, unit: "°C" })] });
ok(T.cardControls(fryer, "appliance", "lg").length === 1, "厨电给目标温度步进");
ok(T.cardControls(dev({}), "camera", "lg").length === 0, "摄像头不虚构控件");

// ---------------------------------------------------------------- 读数 / 曲线选择
const entries = T.readoutEntries(
  dev({ readable: { humidity: {}, temperature: {}, battery_level: {} },
        controls: [ctrl("brightness")] }),
  { temperature: 18.1, humidity: 64, battery_level: 80, brightness: 55, mode: null });
ok(entries.length === 4, "只收有实时值的读数（含可读控件）");
ok(entries[0].key === "temperature" && entries[0].primary, "温度是主读数且排第一");
ok(entries[1].key === "humidity", "湿度排第二");
ok(entries.some((e) => e.key === "brightness"), "可读控件也进读数列表");
ok(!entries.some((e) => e.key === "mode"), "空值读数被过滤");
ok(T.readoutEntries(dev({}), {}).length === 0, "无读数返回空");
// 摄像头参数是控件而非传感器读数：不进读数列表（避免 "夜视 0" 噪声）
const camEntries = T.readoutEntries(
  dev({ controls: [
    ctrl("night-shot", { kind: "enum", svc: "camera-control", label: "夜视",
                         options: [{ v: 0, t: "关闭" }, { v: 2, t: "自动" }] }),
    ctrl("recording-mode", { kind: "enum", svc: "camera-control", label: "录像模式" }) ] }),
  { "night-shot": 2, "recording-mode": 3 });
ok(camEntries.length === 0, "摄像头参数不进读数（只在抽屉控制区呈现）");
// 枚举读数取选项中文名：否则墙壁开关的「模式」会显示成裸数字 0
const modeDev = dev({ controls: [
  ctrl("mode", { kind: "enum", label: "模式",
                 options: [{ v: 0, t: "关闭" }, { v: 1, t: "自动" }] }) ] });
ok(T.readoutEntries(modeDev, { mode: 1 })[0].text === "自动", "枚举读数取中文选项名");
ok(T.readoutEntries(modeDev, { mode: 7 })[0].text === "7", "选项外的枚举值回退数字");
const series = { temperature: [[1, 18], [2, 19], [3, 20]],
                 battery_level: [[1, 80], [2, 80], [3, 79]],
                 brightness: [[1, 50], [2, 60], [3, 70]],
                 motion: [[1, 0], [2, 1]] };
const curves = T.curveEntries(dev({}), series);
ok(curves.length === 1 && curves[0].key === "temperature", "只保留白名单曲线键");
ok(curves[0].last === "20°C", "曲线末值带单位");
ok(T.curveEntries(dev({}), { temperature: [[1, 18]] }).length === 0, "单点不画曲线");
ok(T.curveEntries(dev({}), {}).length === 0, "无历史返回空");

// ---------------------------------------------------------------- SVG 曲线
ok(T.sparkline([]) === "", "空数据返回空串");
const svg = T.sparkline([[1, 18], [2, 19], [3, 17], [4, 20]]);
ok(svg.indexOf("<svg") === 0 && svg.indexOf("</svg>") > 0, "生成完整 SVG");
ok(svg.indexOf("<polyline") > 0 && svg.indexOf("<circle") > 0, "含折线与末点");
ok(svg.indexOf("NaN") < 0 && svg.indexOf("Infinity") < 0, "坐标无 NaN/Infinity");
ok(T.sparkline([[1, 18], [NaN, 19], [3, 20]]).indexOf("<polyline") > 0,
   "脏点被过滤后仍可绘制");
ok(T.sparkline([[1, 5], [2, 5]]).indexOf("<polyline") > 0, "全平数据不除零");
const long = [];
for (let i = 0; i < 200; i++) long.push([i, Math.sin(i / 9) * 10 + 20]);
ok(T.sparkline(long).indexOf("<polyline") > 0, "大量点可绘制");

// ---------------------------------------------------------------- 类别判定修正（③）
ok(C.categoryOf(dev({ model: "xiaomi.fryer.st701",
      controls: [ctrl("target-temperature", { max: 230 })] })) === "appliance",
   "空气炸锅不再误判空调");
ok(C.categoryOf(dev({ model: "viomi.hood.h5",
      controls: [ctrl("fan-level")] })) === "appliance", "油烟机归厨电");
ok(C.categoryOf(dev({ model: "qmi.plug.psv3",
      readable: { temperature: {}, humidity: {} } })) === "outlet",
   "带温湿度的插排仍归插座（读数作为通用能力）");
ok(C.categoryOf(dev({ model: "isa.switch.kg03hl",
      readable: { temperature: {} }, switches: [{}, {}, {}, {}] })) === "switch",
   "带温湿度的屏显开关仍归开关");
ok(C.categoryOf(dev({ model: "loock.lock.t1pro" })) === "camera", "智能门锁归安防");
ok(C.categoryOf(dev({ model: "mibx2.washer.v2",
      readable: { temperature: {} } })) === "appliance", "洗衣机归厨电");
ok(C.categoryOf(dev({ model: "x.unknown", name: "客厅灯" })) === "generic",
   "用户自定义名称不参与分类");
ok(C.categoryOf(dev({ model: "x.unknown",
      readable: { temperature: {} } })) === "climate-sensor", "型号认不出时能力兜底");
ok(C.categoryOf(dev({ model: "x.unknown",
      controls: [ctrl("target-temperature", { max: 230 })] })) === "appliance",
   "目标温度上限很高时兜底判厨电");
ok(C.sizeOf(lamp) === "lg", "带亮度/色温的灯给大卡");
ok(C.sizeOf(dev({ model: "yeelink.light.strip2" })) === "md", "纯灯保持中卡");
ok(C.sizeOf(dev({ model: "qmi.plug.psv3", readable: { temperature: {} } })) === "lg",
   "带趋势读数的插座给大卡显示曲线");
ok(C.hasCurve(dev({ readable: { temperature: {} } })) === true, "温度可画曲线");
ok(C.hasCurve(dev({ readable: { battery_level: {} } })) === false, "电量不占大卡");
ok(Array.isArray(C.CURVE_KEYS) && C.CURVE_KEYS.length > 3, "导出曲线键表");

// ---------------------------------------------------------------- 渲染器 + 交互（轻量 DOM 桩）
function El(tag) {
  const e = {
    tag, className: "", textContent: "", children: [], dataset: {},
    listeners: {}, classList: { add(c) { e.className += " " + c; } },
    appendChild(c) { c.parentNode = e; e.children.push(c); return c; },
    insertBefore(c, ref) {
      c.parentNode = e;
      const i = ref ? e.children.indexOf(ref) : -1;
      if (i < 0) e.children.push(c); else e.children.splice(i, 0, c);
      return c;
    },
    replaceChild(c, old) {
      const i = e.children.indexOf(old);
      if (i >= 0) { e.children[i] = c; c.parentNode = e; }
      return old;
    },
    removeChild(c) {
      const i = e.children.indexOf(c);
      if (i >= 0) { e.children.splice(i, 1); c.parentNode = null; }
      return c;
    },
    addEventListener(type, fn) { e.listeners[type] = fn; },
    get childNodes() { return e.children; },
    get innerHTML() { return e._html || ""; },
    set innerHTML(v) { e._html = v; },
  };
  return e;
}
function findAll(root, cls) {
  const out = [];
  (function walk(node) {
    for (const ch of node.children || []) {
      if ((ch.className || "").split(/\s+/).indexOf(cls) >= 0) out.push(ch);
      walk(ch);
    }
  })(root);
  return out;
}
function makeEl(tag) {
  const e = El(tag);
  e.querySelector = (sel) => findAll(e, sel.replace(/^\./, ""))[0] || null;
  e.querySelectorAll = (sel) => findAll(e, sel.replace(/^\./, ""));
  return e;
}
global.document = { createElement: makeEl };

function fakeBase(d, size) {
  const e = makeEl("div");
  e.className = "device-card"; e.dataset.did = d.did;
  const sub = makeEl("div"); sub.className = "dc-sub";
  sub.appendChild(makeEl("span"));
  e.appendChild(sub);
  if (size === "lg") {
    const detail = makeEl("div"); detail.className = "dc-detail";
    const row = makeEl("div"); row.className = "dc-detail-row";
    const k = makeEl("span"); k.className = "dc-detail-k"; k.textContent = "产品";
    const v = makeEl("span"); v.className = "dc-detail-v"; v.textContent = d.product || "";
    row.appendChild(k); row.appendChild(v); detail.appendChild(row);
    e.appendChild(detail);
    const extra = makeEl("div"); extra.className = "dc-extra"; e.appendChild(extra);
  }
  return e;
}

const series2 = { temperature: [[1, 18], [2, 19], [3, 20]] };
const calls = { set: [], hold: [] };
const deps = {
  baseCard: fakeBase, Cards: C,
  state: { live: { d: { on: true, brightness: 40, "color-temperature": 3800, temperature: 18.1 } },
           history: { d: series2 } },
  setControl: (...a) => calls.set.push(a),
  hold: (...a) => calls.hold.push(a),
};
const renderers = {};
T.install(renderers, deps);
ok(Object.keys(renderers).length === 14, "注册 14 类卡片渲染器");

const cardEl = renderers.light(lamp, "lg");
ok(findAll(cardEl, "ct-tag").length === 0, "类别标签已由类型图标取代（状态行只留状态）");
ok(findAll(cardEl, "ct-controls").length === 1, "灯卡带专属控件区");
ok(findAll(cardEl, "ct-range").length === 2, "大卡有亮度 + 色温两个滑杆");
const range = findAll(cardEl, "ct-range")[0];
range.listeners.pointerdown({ stopPropagation() {} });
ok(calls.hold.length === 1 && calls.hold[0][1] === true, "按下滑杆时锁定卡片不被轮询重建");
range.value = "77";
range.onchange({ stopPropagation() {} });
ok(calls.hold[1] && calls.hold[1][1] === false, "松手后解除锁定");
ok(calls.set.length === 1 && calls.set[0][2] === 77, "滑杆变更下发真实数值");
ok(findAll(cardEl, "ct-chart").length === 0, "灯无传感器曲线时不画空图");

// ---------------------------------------------------------------- 离线卡片
// 参考项目的判据：点了也不会成功的按钮，只会让人以为程序坏了
const offLamp = dev({ online: false, model: "philips.light.sread9",
  controls: [ctrl("brightness"), ctrl("color-temperature", { min: 2700, max: 5500 })],
  readable: { brightness: {}, "color-temperature": {} } });
const offEl = renderers.light(offLamp, "lg");
ok(findAll(offEl, "ct-controls").length === 0, "离线灯卡不摆滑杆");
ok(findAll(offEl, "ct-chart").length === 0, "离线卡不画趋势图");
ok(findAll(offEl, "ct-chart-empty").length === 0, "离线卡不提示曲线采样中");
ok(findAll(offEl, "ct-readouts").length === 1, "离线卡保留最后一次读数");
ok(T.cardControls(offLamp, "light", "lg").length === 2, "控件挑选本身与在线状态无关");

// ---------------------------------------------------------------- 空壳收口
// 尺寸判定只能看设备「声明了什么能力」：声明有读数但实时值没拿到、
// 或者用户手动设过大卡，都会渲染成一块占两列的空板子。收成单格。
const bareDev = dev({ did: "bare", model: "xiaomi.repeater.v3",
                      controls: [], readable: {}, switches: [] });
const bareEl = renderers.hub(bareDev, "lg");
ok((bareEl.className || "").indexOf("is-bare") >= 0, "空壳大卡标记 is-bare 收成单格");
ok(findAll(bareEl, "dc-detail").length === 0, "空壳卡移除设备档案行");
ok(findAll(bareEl, "dc-extra").length === 0, "空壳卡移除扩展位");
ok(findAll(bareEl, "ct-readouts").length === 0, "空壳卡没有读数区");
const bareMd = renderers.hub(bareDev, "md");
ok((bareMd.className || "").indexOf("is-bare") >= 0, "空壳中卡同样收口");

const sensorDev = dev({ model: "miaomiaoce.sensor_ht.t2",
  readable: { temperature: {}, humidity: {} }, controls: [], switches: [] });
const sensorEl = renderers["climate-sensor"](sensorDev, "lg");
ok((sensorEl.className || "").indexOf("is-bare") < 0, "有读数的卡不收口");
ok(findAll(sensorEl, "ct-readouts").length === 1, "温湿度卡带读数区");
ok(findAll(sensorEl, "ct-chart").length === 1, "温湿度卡带趋势图");
ok((findAll(sensorEl, "ct-chart-svg")[0].innerHTML || "").indexOf("<svg") >= 0,
   "趋势图内嵌 SVG 折线");
ok(findAll(sensorEl, "ct-info").length === 1, "有内容的卡把 4 行档案压成一行");

const smallEl = renderers.switch(dev({ model: "lumi.ctrl_neutral2.v1" }), "sm");
ok(findAll(smallEl, "ct-readouts").length === 0 &&
   findAll(smallEl, "ct-controls").length === 0, "小卡只留名称/开关/状态");

const block = T.historyBlock(sensorDev, series2, 24, () => {});
ok(findAll(block, "dr-h-item").length === 1, "抽屉生成一条历史曲线");
ok((findAll(block, "ct-chart-svg")[0].innerHTML || "").indexOf("<polyline") >= 0,
   "抽屉曲线含折线");
ok(findAll(block, "dr-h-ranges")[0].children.length === 3, "抽屉有 3 个时间范围按钮");
ok(findAll(T.historyBlock(sensorDev, {}, 24, () => {}), "ct-chart-empty").length === 1,
   "无历史时给出采样提示");

console.log("card_types_test: " + n + " 项通过");
