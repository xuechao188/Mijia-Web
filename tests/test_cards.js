/* 设备类别 / 卡片尺寸判定回归（Node 直接跑，无浏览器依赖）。 */
"use strict";
const C = require("../static/cards.js");

let n = 0;
function ok(cond, msg) {
  if (!cond) throw new Error(msg);
  n++;
}
function dev(model, extra) {
  return Object.assign({ did: "d", name: "n", model: model, product: "" }, extra || {});
}

const cases = [
  ["yeelink.light.strip2", "light", "md"],
  ["philips.light.sread9", "light", "md"],
  ["zbmesh.light.wy0a02", "light", "md"],
  ["miaomiaoce.sensor_ht.t2", "climate-sensor", "lg"],
  ["090615.switch.mesw2", "switch", "sm"],
  ["lumi.ctrl_neutral2.v1", "switch", "sm"],
  ["chuangmi.plug.v1", "outlet", "sm"],
  ["chuangmi.camera.v2", "camera", "md"],
  ["loock.cateye.v02", "camera", "md"],
  ["lumi.acpartner.v3", "climate", "lg"],
  ["rockrobo.vacuum.v1", "cleaner", "lg"],
  ["zhimi.airpurifier.v1", "purifier", "lg"],
  ["miir.remote.ir01", "ir", "sm"],       // 红外遥控自成一类，不再混进网关
  ["xiaomi.router.v1", "hub", "sm"],
  ["lumi.sensor_motion.aq2", "sensor", "sm"],
  ["cuco.plug.cp1", "outlet", "sm"],
  ["some.unknown.thing", "generic", "sm"],
];
for (const [model, cat, size] of cases) {
  const d = dev(model);
  ok(C.categoryOf(d) === cat, model + " 类别应为 " + cat + "，实为 " + C.categoryOf(d));
  ok(C.sizeOf(d) === size, model + " 尺寸应为 " + size + "，实为 " + C.sizeOf(d));
}

// 能力优先：spec 修好后不依赖型号也能精确判定
ok(C.categoryOf(dev("x.y.z", { controls: [{ key: "brightness" }] })) === "light",
   "有亮度控件应判为灯");
ok(C.categoryOf(dev("x.y.z", { readable: { temperature: null } })) === "climate-sensor",
   "有温度读数应判为环境传感器");
ok(C.categoryOf(dev("x.y.z", { controls: [{ key: "target-temperature" }] })) === "climate",
   "有目标温度应判为空调");
ok(C.sizeOf(dev("x.y.z", { controls: [{ key: "a" }, { key: "b" }] })) === "md",
   "通用类别有两个控件应给中卡");

// 离线降档：控件整块不渲染后，大卡只剩「图标 + 名称 + 离线」一块空板子，
// 空占 2×2 格却什么也不给。按有没有读数收到中卡 / 小卡。
ok(C.sizeOf(dev("miaomiaoce.sensor_ht.t2", { online: false })) === "sm",
   "离线且无读数给小卡");
ok(C.sizeOf(dev("miaomiaoce.sensor_ht.t2",
                { online: false, readable: { temperature: null } })) === "md",
   "离线但有读数给中卡");
ok(C.sizeOf(dev("zhimi.airpurifier.v1",
                { online: false, controls: [{ key: "mode" }] })) === "md",
   "离线净化器原本大卡，降为中卡");
ok(C.sizeOf(dev("miaomiaoce.sensor_ht.t2")) === "lg",
   "在线仍保留大卡（离线规则不误伤在线设备）");
ok(C.sizeOf(dev("zhimi.airpurifier.v1", { online: true })) === "lg",
   "在线净化器仍是大卡");

// 兜底与标签完整性
ok(C.categoryOf(null) === "generic" && C.sizeOf(null) === "sm", "空输入兜底");
ok(C.categoryOf(dev("")) === "generic", "空型号兜底");
for (const m of ["yeelink.light.strip2", "miaomiaoce.sensor_ht.t2", "some.unknown.thing"]) {
  const c = C.categoryOf(dev(m));
  ok(typeof C.CATEGORY_LABELS[c] === "string", "类别 " + c + " 应有中文名");
}

// toggleable：仅以开关为主控的品类、且确有开关属性时才显示电源开关
ok(C.toggleable(dev("chuangmi.plug.v1", { switches: [{ key: "on" }] })) === true,
   "插座有开关→可开关");
ok(C.toggleable(dev("yeelink.light.strip2", { switches: [{ key: "on" }] })) === true,
   "灯有开关→可开关");
ok(C.toggleable(dev("zhimi.airpurifier.v1", { switches: [{ key: "on" }] })) === false,
   "净水器/净化器即使有开关也不应在卡片显示电源开关");
ok(C.toggleable(dev("miir.remote.ir01", { switches: [{ key: "on" }] })) === false,
   "网关/音箱/WiFi 不应显示电源开关");
ok(C.toggleable(dev("chuangmi.camera.v2", { switches: [{ key: "on" }] })) === false,
   "摄像头不应显示电源开关");
ok(C.toggleable(dev("lumi.sensor_motion.aq2", { switches: [{ key: "on" }] })) === false,
   "传感器不应显示电源开关");
ok(C.toggleable(dev("chuangmi.plug.v1", {})) === false,
   "无开关属性的设备不可开关");

console.log("cards_test: " + n + " 项通过");
