/* 登录页小猫回归：心情映射 / 瞳孔跟随 / 台词轮换 / SVG 结构 / 安装与状态切换。
 * Node 直接跑，DOM 用轻量桩——这个模块只碰 innerHTML、dataset、classList 三样。 */
"use strict";
const C = require("../static/login_cat.js");

let n = 0;
function ok(cond, msg) {
  if (!cond) throw new Error("✗ " + msg);
  n++;
}

// ---------------------------------------------------------------- 心情映射
ok(C.moodOf("请使用米家 App 扫码", "") === "wait", "等扫码 → wait");
ok(C.moodOf("登录成功，正在进入…", "ok") === "ok", "成功文案 + ok 类 → ok");
ok(C.moodOf("随便什么", "ok") === "ok", "ok 类优先于文案");
ok(C.moodOf("二维码已过期", "err") === "err", "过期 → err");
ok(C.moodOf("获取失败", "") === "err", "失败文案 → err");
ok(C.moodOf("扫码登录出错", "") === "err", "出错文案 → err");
ok(C.moodOf("正在获取二维码…", "") === "idle", "取码中 → idle");
ok(C.moodOf("正在检查登录状态…", "") === "idle", "检查状态 → idle");
ok(C.moodOf("正在恢复登录（等待小米风控解除）…", "") === "idle", "恢复登录 → idle（不打扰）");
ok(C.moodOf(null, undefined) === "idle", "空输入安全回落 idle");
ok(C.moodOf(undefined, null) === "idle", "undefined 安全回落 idle");
ok(C.moodOf("登录成功，正在进入…", "") === "ok", "无 cls 时也能从文案认出成功");
ok(C.MOODS.join(",") === "idle,wait,ok,err", "四种心情固定顺序");

// ---------------------------------------------------------------- 瞳孔跟随
let s = C.pupilShift(100, 100, 100, 100, 2.6);
ok(s.x === 0 && s.y === 0, "鼠标在眼睛正中：不偏移");
s = C.pupilShift(200, 100, 100, 100, 2.6);
ok(s.x > 0 && Math.abs(s.y) < 0.01, "鼠标在右侧：瞳孔向右");
s = C.pupilShift(100, 20, 100, 100, 2.6);
ok(s.y < 0 && Math.abs(s.x) < 0.01, "鼠标在上方：瞳孔向上");
s = C.pupilShift(100, 100, 100, 100, 2.6);
ok(Math.sqrt(s.x * s.x + s.y * s.y) <= 2.6, "偏移不超过上限");
[4000, -4000, 99999].forEach((v) => {
  const p = C.pupilShift(v, v, 0, 0, 2.6);
  ok(Math.sqrt(p.x * p.x + p.y * p.y) <= 2.61, "远距离也封顶在 max 内（" + v + "）");
});
s = C.pupilShift(0, 0, 0, 0, 2.6);
ok(s.x === 0 && s.y === 0, "零距离不除零");
s = C.pupilShift(NaN, 3, 0, 0, 2.6);
ok(s.x === 0 && s.y === 0, "NaN 输入安全返回 0");
s = C.pupilShift(1000, 1000, 0, 0, 1);
ok(Math.sqrt(s.x * s.x + s.y * s.y) <= 1.01, "自定义上限生效");
s = C.pupilShift(1000, 1000, 0, 0, 0);
ok(Math.sqrt(s.x * s.x + s.y * s.y) <= 2.61, "非法上限回落默认 2.4");

// ---------------------------------------------------------------- 台词
ok(typeof C.pickLine("idle", 0) === "string", "idle 有台词");
ok(C.LINES.wait.indexOf(C.pickLine("wait", 3)) >= 0, "wait 台词来自对应分组");
ok(C.pickLine("idle", 0) === C.pickLine("idle", C.LINES.idle.length), "台词循环不越界");
ok(C.pickLine("idle", 1) !== C.pickLine("idle", 2), "相邻两次换一句");
ok(C.LINES.idle.indexOf(C.pickLine("不存在的分组", 0)) >= 0, "未知心情回落 idle 台词");
ok(C.pickLine("err", -5) === C.pickLine("err", Math.abs(-5) % C.LINES.err.length),
   "负数下标按绝对值取模");
ok(C.pickLine("ok", "3") === C.pickLine("ok", 0), "字符串下标按位数（3 % 3）");

// ---------------------------------------------------------------- SVG 结构
const svg = C.svg();
ok(svg.indexOf("<svg") === 0, "svg() 返回 svg 根元素");
ok(svg.indexOf('viewBox="0 0 200 120"') > 0, "有 viewBox（可缩放）");
ok(svg.indexOf('fill="none"') > 0,
   "svg 根带 fill=none（pico 有 svg:not([fill]){fill:currentColor}，不写死深色主题会变白）");
ok(svg.indexOf('aria-label="登录页的小猫"') > 0, "有 aria-label");
ok(svg.indexOf("<img") < 0, "不依赖外部图片（离线可用）");
ok(!/[\u{1F300}-\u{1FAFF}\u{2600}-\u{27BF}]/u.test(svg), "不用 emoji 当图形");
ok((svg.match(/<g\b/g) || []).length === (svg.match(/<\/g>/g) || []).length, "<g> 配平");
["cat-tail", "cat-body", "cat-head", "cat-face", "cat-eyeball", "cat-glint",
 "eye-happy", "cat-nose", "cat-mouth", "cat-whiskers", "cat-blush", "cat-ear",
 "cat-paw", "cat-tuft", "cat-shadow", "cat-brow", "cat-mouth-sad"].forEach((cls) => {
  ok(svg.indexOf('class="' + cls) > 0 || svg.indexOf(" " + cls + '"') > 0,
     "含 " + cls + "（CSS 靠它上色/做动效）");
});
ok((svg.match(/cat-eyeball/g) || []).length === 2, "两只眼睛都有 cat-eyeball");
ok((svg.match(/cat-ear-in/g) || []).length === 2, "两只耳朵都有粉色内耳");
const brow = (svg.match(/<path class="cat-brow" d="([^"]+)"/) || [])[1] || "";
ok((brow.match(/M/g) || []).length === 2, "失落态一条 path 画出左右两根眉毛");
ok(svg.indexOf('<g class="cat-sad">') > 0, "失落态表情收在一个 cat-sad 组里（便于整体开关）");
ok(svg.indexOf('class="eyeball"') < 0, "不再有裸 class=eyeball（会被 pico 的 fill 规则吃掉）");

// ---------------------------------------------------------------- 安装（轻量 DOM 桩）
function node(cls) {
  const el = {
    className: cls || "", textContent: "", innerHTML: "", dataset: {},
    tabIndex: 0, offsetWidth: 1,
    style: { setProperty() {} },
    _attrs: {},
    classList: {
      add(c) { if (!el.classList.contains(c)) el.className = (el.className + " " + c).trim(); },
      remove(c) { el.className = (" " + el.className + " ").replace(" " + c + " ", " ").trim(); },
      contains(c) { return (" " + el.className + " ").indexOf(" " + c + " ") >= 0; },
      toggle(c, on) { on ? el.classList.add(c) : el.classList.remove(c); },
    },
    addEventListener(t, fn) { (el._ev = el._ev || {})[t] = fn; },
    setAttribute(k, v) { el._attrs[k] = v; },
    querySelector() { return null; },
  };
  return el;
}
function mount() {
  const bubble = node("cat-say");
  const svgEl = node("lp-cat-svg");
  const m = node("");
  m.querySelector = (sel) => (sel === ".cat-say" ? bubble : (sel === ".lp-cat-svg" ? svgEl : null));
  m._bubble = bubble;
  return m;
}

ok(C.install({}) === C, "没有挂载点也不崩");
const m1 = mount();
C.install({ mount: m1 });
ok(m1.classList.contains("lp-cat"), "安装后挂上 lp-cat 类");
ok(m1.dataset.mood === "idle", "初始心情 idle");
ok(m1.innerHTML.indexOf("<svg") === 0, "innerHTML 注入猫本体");
ok(m1.innerHTML.indexOf("cat-say") > 0, "inject 气泡容器");
ok(m1._attrs.title === "点一下", "给了一个可点提示");
ok(m1.tabIndex === 0, "可键盘聚焦");

C.setMood("wait");
ok(m1.dataset.mood === "wait", "setMood 切到 wait");
C.setMood("乱写的心情");
ok(m1.dataset.mood === "idle", "非法心情回落 idle");
C.setMood("ok");
ok(m1.dataset.mood === "ok", "setMood 切到 ok");

// 说话
const said = C.say("喵", 1000);
ok(said === "喵", "say 返回说出的内容");
ok(m1._bubble.textContent === "喵", "气泡文字更新");
ok(m1._bubble.classList.contains("show"), "气泡显示");
ok(C.say("") === "", "空台词也不炸");

// 点猫：先说一句，再进入「被戳」状态
C.setMood("wait");
const line = C.poke();
ok(C.LINES.wait.indexOf(line) >= 0, "点猫说的第一句是 wait 分组台词");
ok(m1._bubble.textContent === line, "点猫立刻显示台词");
ok(m1.classList.contains("is-poked"), "点猫加上抖动类");

// ---------------------------------------------------------------- 登录成功的跳一下
const timers = [];
const realSetTimeout = global.setTimeout;
const realClearTimeout = global.clearTimeout;
global.setTimeout = (fn, ms) => { timers.push({ fn, ms }); return timers.length; };
global.clearTimeout = () => {};
C.reset();
let done = 0;
const waitMs = C.playIn(700, () => { done++; });
ok(waitMs === 700, "playIn 返回等待时长");
ok(C.mood === "ok", "成功时猫进入 ok 心情");
ok(done === 0, "跳之前不急着收页");
timers.filter((t) => t.ms === 700).forEach((t) => t.fn());
ok(done === 1, "跳完调 done 一次");
let done2 = 0;
C.playIn(700, () => { done2++; });
ok(done2 === 1, "重复调用直接走 done，不叠加延迟");
C.reset();
let done0 = 0;
ok(C.playIn(0, () => { done0++; }) === 0, "允许 0 毫秒（不等待）");
timers.filter((t) => t.ms === 0).forEach((t) => t.fn());
ok(done0 === 1, "0 毫秒也会收尾");

C.reset();
let done3 = 0;
C.playIn(undefined, () => { done3++; });
ok(timers.filter((t) => t.ms === 700).length >= 2, "不传时长按 700ms");
timers.slice(-1).forEach((t) => t.fn());
ok(done3 === 1, "默认时长也能收尾");

global.setTimeout = realSetTimeout;
global.clearTimeout = realClearTimeout;
C.reset();

// 不传 done 也不能炸
C.playIn(0);
ok(true, "没有回调也安全");

console.log("login_cat 测试通过：" + n + " 项");
