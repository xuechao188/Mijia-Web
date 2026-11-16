/* 摄像头动作分类纯函数回归（Node 直接跑，无 DOM 依赖）。 */
"use strict";
const CP = require("../static/camera_panel.js");

let n = 0;
function ok(cond, msg) {
  if (!cond) throw new Error(msg);
  n++;
}

// chuangmi.camera.v2 真实动作：start/stop 取流 + format（破坏性）+ pop-up
const chuangmi = [
  { siid: 3, aiid: 1, name: "start-p2p-stream", svc: "p2p-stream" },
  { siid: 3, aiid: 2, name: "stop-stream", svc: "p2p-stream" },
  { siid: 6, aiid: 1, name: "format", svc: "memory-card-management" },
  { siid: 6, aiid: 2, name: "pop-up", svc: "memory-card-management" },
];
let r = CP.classify(chuangmi);
ok(r.ptz.length === 0, "旧款创米摄像头：无云台动作（ptz=0）");
ok(r.others.length === 0, "format/pop-up 被拦截，others=0");
ok(r.denied.length === 2, "format/pop-up 归入 denied（不暴露按钮）");

// 带标准云台动作的摄像头
const ptzCam = [
  { siid: 2, aiid: 1, name: "pan-left", svc: "camera-control" },
  { siid: 2, aiid: 2, name: "pan-right", svc: "camera-control" },
  { siid: 2, aiid: 3, name: "tilt-up", svc: "camera-control" },
  { siid: 2, aiid: 4, name: "tilt-down", svc: "camera-control" },
  { siid: 2, aiid: 5, name: "zoom-in", svc: "camera-control" },
  { siid: 2, aiid: 6, name: "zoom-out", svc: "camera-control" },
  { siid: 3, aiid: 1, name: "start-p2p-stream", svc: "p2p-stream" },
];
r = CP.classify(ptzCam);
ok(r.ptz.length === 6, "标准云台摄像头：6 个 PTZ 动作识别");
ok(r.ptz.every((a) => CP.PTZ_SYMBOLS[a.name]), "PTZ 动作都有方向符号");
ok(r.others.length === 0, "取流动作不进 others");

// 安全白名单内的其它动作
r = CP.classify([{ siid: 2, aiid: 9, name: "snapshot", svc: "camera-control" },
                 { siid: 2, aiid: 10, name: "led", svc: "camera-control" }]);
ok(r.others.length === 2, "snapshot/led 归入 others（安全可控）");

// 未知动作保守不暴露
r = CP.classify([{ siid: 2, aiid: 99, name: "mystery-action", svc: "camera-control" }]);
ok(r.denied.length === 1 && r.others.length === 0, "未知动作保守归入 denied");

// 空/缺省
ok(CP.classify(null).ptz.length === 0, "空动作列表安全返回");

// ---------------------------------------------------------------- 渲染（轻量 DOM 桩）
function El(tag) {
  const e = {
    tag, className: "", textContent: "", children: [], dataset: {}, disabled: false,
    classList: {
      add(c) { e.className += " " + c; },
      remove(c) { e.className = (" " + e.className + " ").replace(" " + c + " ", " ").trim(); },
      toggle(c, on) { if (on) e.classList.add(c); else e.classList.remove(c); },
    },
    appendChild(c) { c.parentNode = e; e.children.push(c); return c; },
    addEventListener() {}, set onclick(fn) { e._click = fn; }, get onclick() { return e._click; },
    play() { return { catch() {} }; },
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
global.document = { createElement: El };

function createEl(tag, cls, text) {
  const e = El(tag); if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

let apiCalls = [];
const fakeState = { cameraStream: {} };
CP.install({
  state: fakeState,
  createEl,
  toast() {},
  api(path, body) { apiCalls.push(path); return Promise.resolve({ ok: true, playable: false, note: "n" }); },
});

// 旧款创米：无云台 → 出现说明文字，不出现 cam-pad
let node = CP.render({ did: "cam1", actions: chuangmi });
ok(findAll(node, "cam-video").length === 1, "渲染出实时画面区");
ok(findAll(node, "cam-btns").length === 1, "渲染出取流/停止按钮行");
ok(findAll(node, "cam-pad").length === 0, "无云台动作：不渲染方向盘");
const notes = findAll(node, "cam-note").map((x) => x.textContent).join("");
ok(notes.indexOf("未在 MIoT 标准协议") >= 0, "无云台动作：给出明确说明");

// 标准云台摄像头：出现方向盘 + 5 个方向格
node = CP.render({ did: "cam2", actions: ptzCam });
const grid = findAll(node, "cam-pad-grid")[0];
ok(!!grid, "有云台动作：渲染方向盘");
ok(grid.children.length === 5, "方向盘 5 个格子（上左右下+中）");
const enabled = grid.children.filter((c) => !c.disabled).length;
ok(enabled === 4, "仅存在 4 个方向动作时启用 4 格（zoom 不进方向盘）");

// 取流按钮触发 /api/camera/stream
apiCalls = [];
node = CP.render({ did: "cam3", actions: chuangmi });
const btns = findAll(node, "cam-btns")[0].children;
btns[0].onclick();
ok(apiCalls.indexOf("/api/camera/stream") >= 0, "点击取流按钮调用 /api/camera/stream");

console.log("camera_panel 测试通过：%d 项", n);
