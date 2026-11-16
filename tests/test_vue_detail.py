#!/usr/bin/env python3
"""Vue 详情增强（步骤⑤）不变量：摄像头专项。

1) 运行时交叉校验：Node 22 --experimental-strip-types 直接加载
   web/src/devices/camera.ts，与旧界面 camera_panel.js 的同一套规则逐项比对。
2) 静态文本：组件接线、端点、样式钩子、旧前端零牵连。
3) 定时规则已整体下线：前后端与旧界面都不再留入口（见第 3 节）。
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "web", "src")

ok_n = [0]


def ok(cond, msg):
    ok_n[0] += 1
    if not cond:
        print("✗ " + msg)
        sys.exit(1)
    print("✓ " + msg)


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def path(*parts):
    return os.path.join(*parts)


PURE = ["devices/camera.ts"]

# ---- 1. 纯逻辑模块齐全 ----
for rel in PURE:
    ok(os.path.isfile(path(SRC, *rel.split("/"))), "新增 %s" % rel)

with tempfile.TemporaryDirectory(prefix="vue_detail_") as tmp:
    for rel in PURE:
        text = read(path(SRC, *rel.split("/")))
        open(path(tmp, rel.split("/")[-1]), "w", encoding="utf-8").write(text)

    probe = r'''
const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
const [ROOT, TMP] = process.argv.slice(2);
const CP = require(ROOT + '/static/camera_panel.js');
const cam = await import('file://' + TMP + '/camera.ts');

let total = 0; const fail = [];
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function push(msg, cond) { total++; if (!cond) fail.push(msg); }

/* ---------- DOM 桩：复用旧版 applyStream 的真实行为 ---------- */
function El(tag) {
  const e = {
    tag, className: '', textContent: '', children: [], src: '',
    classList: {
      add(c) { e.className += ' ' + c; },
      remove(c) { e.className = (' ' + e.className + ' ').replace(' ' + c + ' ', ' ').trim(); },
      contains(c) { return e.className.split(/\s+/).includes(c); },
    },
    appendChild(c) { c.parentNode = e; e.children.push(c); return c; },
    play() { return { catch() {} }; },
  };
  return e;
}
globalThis.document = { createElement: El };
function oldApply(r) {
  const video = El('video'), ph = El('div'), note = El('div');
  CP.applyStream(video, ph, note, r);
  const raw = note.children.find((c) => c.tag === 'details');
  const pre = raw && raw.children.find((c) => c.tag === 'pre');
  return { playable: !video.classList.contains('hidden'), url: video.src,
           note: note.textContent, rawText: pre ? pre.textContent : null };
}

/* ---------- 摄像头：常量同源 ---------- */
push('PTZ_SYMBOLS 与旧版一致', eq(cam.PTZ_SYMBOLS, CP.PTZ_SYMBOLS));
push('SAFE_ACTION 与旧版一致', cam.SAFE_ACTION.source === CP.SAFE_ACTION.source);
push('DENY_ACTION 与旧版一致', cam.DENY_ACTION.source === CP.DENY_ACTION.source);
push('DIRECTIONS 与旧版一致', eq(Array.from(cam.DIRECTIONS), CP.DIRECTIONS));

/* ---------- 摄像头：动作分类逐项比对 ---------- */
const A = (name, aiid, svc) => ({ siid: 3, aiid, name, svc: svc || 'camera-control' });
const sets = [
  [],
  null,
  [A('start-p2p-stream', 1, 'p2p-stream'), A('stop-stream', 2, 'p2p-stream')],
  [A('format', 1, 'memory-card-management'), A('pop-up', 2, 'memory-card-management')],
  [A('pan-left', 1), A('pan-right', 2), A('tilt-up', 3), A('tilt-down', 4),
   A('zoom-in', 5), A('zoom-out', 6), A('rotate', 7), A('ptz', 8)],
  [A('snapshot', 9), A('led', 10), A('mystery-action', 11)],
  [A('PAN-LEFT', 12), A('reset', 13), A('delete', 14), A('enable', 15),
   A('disable', 16), A('go-to-preset', 17), A('ptz-control', 18)],
  [A('snapshot', 19), A('start-p2p-stream', 20, 'p2p-stream'), A('format', 21),
   A('tilt-up', 22)],
];
for (let i = 0; i < sets.length; i++) {
  const s = sets[i];
  push('classify 集合 ' + i + ' 与旧版一致', eq(cam.classify(s), CP.classify(s)));
}
// 随机组合再压一轮，防止白名单边界漏判
const names = ['pan-left','tilt-down','zoom-in','rotate','go-to-preset','ptz',
               'snapshot','calibration','flip','mirror','led','indicator','alarm',
               'siren','notify','mute','volume','talk','push','enable','disable',
               'move','format','delete','reset','factory','restore','reboot',
               'power-off','pop-up','eject','clear','remove','add','mystery',''];
for (let k = 0; k < 40; k++) {
  const s = [];
  for (let j = 0; j < 6; j++) {
    const name = names[(k * 7 + j * 5) % names.length];
    s.push(A(name, j + 1, j % 5 === 0 ? 'p2p-stream' : 'camera-control'));
  }
  push('classify 组合 ' + k + ' 与旧版一致', eq(cam.classify(s), CP.classify(s)));
}
for (let i = 0; i < cam.DIRECTIONS.length; i++) {
  const name = cam.DIRECTIONS[i];
  const sample = [A('pan-left', 1), A('tilt-up', 2), A('ptz', 3)];
  const found = cam.directionAction(name, sample);
  const manual = sample.find((a) => a.name === name) || null;
  push('directionAction ' + name, eq(found, manual));
}
push('directionAction 缺项返回 null', cam.directionAction('zoom-in', [A('pan-left', 1)]) === null);

/* ---------- 摄像头：取流文案逐项比对 ---------- */
const results = [
  { ok: true, playable: true, url: 'http://x/live.m3u8', note: 'ignored', raw: { a: 1 } },
  { ok: true, playable: false, note: '小米专有 P2P，不能播', raw: { token: 'abc' } },
  { ok: true, playable: false, raw: null },
  { ok: true, playable: false, raw: [1, 2, 3] },
  { ok: true, playable: false, note: null, raw: 'plain' },
  { ok: true, playable: true, url: '' },
];
for (let i = 0; i < results.length; i++) {
  const r = results[i], o = oldApply(r), n = cam.streamView(r);
  push('streamView ' + i + ' mode', (n.mode === 'playable') === o.playable);
  push('streamView ' + i + ' url', (n.url || '') === (o.url || ''));
  push('streamView ' + i + ' note', n.note === o.note);
  push('streamView ' + i + ' rawText', (n.rawText || null) === (o.rawText || null));
}
push('streamFailure 优先 hint', cam.streamFailure({ hint: '稍后再试', error: 'e' }) === '取流失败：稍后再试');
push('streamFailure 回落 error', cam.streamFailure({ error: 'e' }) === '取流失败：e');
push('streamFailure 缺省不炸', cam.streamFailure({}) === '取流失败：');
push('常量：空闲占位', cam.PLACEHOLDER_IDLE === '实时画面需从设备取流');
push('常量：失败占位', cam.PLACEHOLDER_FAILED === '该设备无法在 PC 浏览器直接出画面');
push('常量：原始返回折叠标题', cam.RAW_SUMMARY === '查看设备返回的原始数据');
push('常量：无云台说明', cam.NO_PTZ_NOTE.indexOf('未在 MIoT 标准协议') >= 0);

/* ---------- 取流能力判定：结论 → 界面三件套 ---------- */
const capCases = [
  ['wan', true, 'ok'],
  ['lan', true, 'warn'],
  ['lan_only', false, 'warn'],
  ['unsupported', false, 'muted'],
  ['offline', false, 'muted'],
  ['unknown', true, 'muted'],
];
for (const [mode, canTry, tone] of capCases) {
  const v = cam.capView({ mode, title: 'T', reason: 'R', advice: 'A' });
  push('capView ' + mode + ' canTry', v.canTry === canTry);
  push('capView ' + mode + ' tone', v.tone === tone);
  push('capView ' + mode + ' detail 拼接', v.detail === 'RA');
}
push('capView 空值安全', cam.capView(null) === null && cam.capView({}) === null);
push('lan_only 占位文案讲清局域网',
  cam.capView({ mode: 'lan_only' }).placeholder.indexOf('局域网') >= 0);
push('unsupported 占位文案讲清不支持',
  cam.capView({ mode: 'unsupported' }).placeholder.indexOf('不支持') >= 0);
push('wan 不误报「需同局域网」',
  cam.capView({ mode: 'wan' }).placeholder.indexOf('局域网') < 0);
push('vendorLabel tutk', cam.vendorLabel('tutk') === 'TUTK 固件');
push('vendorLabel 未知型号原样大写', cam.vendorLabel('xyz') === 'XYZ');
push('vendorLabel 空值', cam.vendorLabel(null) === '');

push('capDialog lan_only 主行动说「连到同一网络」',
  cam.capDialog({ mode: 'lan_only', title: 'T', reason: 'R', advice: 'A', vendor: 'tutk' })
    .action === '我已连到同一网络');
push('capDialog 原因与建议分两段',
  (() => {
    const d = cam.capDialog({ mode: 'unsupported', title: 'T', reason: 'R', advice: 'A' });
    return d.reason === 'R' && d.advice === 'A' && d.note === '';
  })());
push('capDialog 固件标签复用 vendorLabel',
  cam.capDialog({ mode: 'lan_only', vendor: 'tutk' }).vendor === 'TUTK 固件');
push('capDialog 非局域网结论给「重新检测」',
  cam.capDialog({ mode: 'offline' }).action === '重新检测');
push('capDialog 无判定时用兜底标题 + 原样说明',
  (() => {
    const d = cam.capDialog(null, '网络异常');
    return d.title === cam.CAP_TIP_FALLBACK && d.note === '网络异常' && d.reason === '';
  })());
push('capDialog 无判定无说明也不空转', cam.capDialog(null).note.length > 0);
push('capDialog tone 随 mode', cam.capDialog({ mode: 'lan_only' }).tone === 'warn');

console.log(JSON.stringify({ total, fail }));
'''
    probe_path = path(tmp, "probe_detail.mjs")
    with open(probe_path, "w", encoding="utf-8") as f:
        f.write(probe)
    proc = subprocess.run(
        ["node", "--experimental-strip-types", probe_path, ROOT, tmp],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
        sys.exit(1)
    import json
    payload = {}
    for line in proc.stdout.strip().splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
    ok(payload.get("fail") == [], "Node 运行时交叉校验 %s 项全过：%s" % (
        payload.get("total", 0), (payload.get("fail") or [])[:6]))
    for _ in range(int(payload.get("total", 0))):
        ok_n[0] += 1

# ---- 2. 组件与外壳接线 ----
FILES = [
    "components/CameraPanel.vue", "stores/detail.ts",
]
text = {}
for rel in FILES:
    text[rel] = read(path(SRC, *rel.split("/")))
    ok(len(text[rel]) > 800, "新增/改造 %s" % rel)

# 定时规则整体下线：组件与纯逻辑模块都已删除，不再有第二套「按时开关」
for gone in ["components/SchedPanel.vue", "devices/sched.ts"]:
    ok(not os.path.isfile(path(SRC, *gone.split("/"))), "定时模块已删除 %s" % gone)

cam_vue = text["components/CameraPanel.vue"]
for needle in ["useDetailStore", "classify(", "directionAction(", "streamView(",
               "detail.getStream(", "detail.stopStream(", "detail.runAction(",
               "cam-video-el", "cam-placeholder", "cam-btns", "cam-pad-grid",
               "cam-pad-btn", "NO_PTZ_NOTE", "DIRECTIONS"]:
    ok(needle in cam_vue, "CameraPanel 接线 %s" % needle)
ok("cls.denied" not in cam_vue and "DENY_ACTION" not in cam_vue,
   "摄像头面板零暴露破坏性动作")
ok("v-html" not in cam_vue, "摄像头面板不注入未转义 HTML")

# 取流能力：不常驻面板 —— 点按钮时才判，播不了才弹窗
for needle in ["detail.caps", "capView(cap.value)", "PLACEHOLDER_IDLE"]:
    ok(needle in cam_vue, "CameraPanel 按需取判定 %s" % needle)
ok("cam-cap" not in cam_vue and "cam-cap-why" not in cam_vue,
   "面板里不再常驻能力状态条")
ok("onMounted(" not in cam_vue and "checkCapability(" not in cam_vue,
   "打开面板不预先检测，检测只在点击后发生")
ok(':disabled="busy"' in cam_vue, "取流按钮始终可点，只有请求进行中禁用")
ok("正在检测" in cam_vue, "点击后如实显示正在检测")
ok("detail.tip" not in cam_vue and "CapDialog" not in cam_vue,
   "弹窗挂在抽屉遮罩层，面板内部不自渲染")
ok(":src=\"view?.url || ''\"" in cam_vue, "视频源仍只认后端给的可播地址")
ok("fetch(" not in cam_vue, "CameraPanel 不绕过数据层直接发请求")

# 数据层：能力判定按 did 缓存 + 弹窗承接播不了的原因
detail_ts = text["stores/detail.ts"]
for needle in ["caps", "capBusy", "capError", "checkCapability",
               "/api/camera/capability", "force=1", "tip.value = {",
               "closeTip", "retryTip"]:
    ok(needle in detail_ts, "detail store 能力判定接线 %s" % needle)
ok("r.playable && r.url" in detail_ts, "只有拿到可播地址才写入 streams")
ok("streamNotes.value = { ...streamNotes.value, [did]: '' }" in detail_ts,
   "播不了时不在面板留文字说明，交给弹窗")

cap_py = read(path(ROOT, "services", "camera_cap.py"))
for needle in ["miss_get_vendor", "localip", "p2p_id", "same_lan",
               "VENDOR_PC_OK", "_lan_reachable", "32761"]:
    ok(needle in cap_py, "camera_cap 判定链 %s" % needle)
ok("lan_only" in cap_py and "仅支持局域网" in cap_py, "老固件判定为仅局域网")
cam_routes = read(path(ROOT, "routes", "camera.py"))
ok('@bp.route("/api/camera/capability"' in cam_routes, "能力查询接口已注册")
ok("camera_cap.assess(did)" in cam_routes, "取流前先做能力判定")

drawer = read(path(SRC, "components", "DeviceDrawer.vue"))
for needle in ["CameraPanel", "isCamera", ":device=\"d\""]:
    ok(needle in drawer, "DeviceDrawer 接入 %s" % needle)
ok("步骤 ⑥" not in drawer and "将在步骤" not in drawer, "抽屉里不再留 ⑤ 的待迁占位")

# 居中双列弹框：外壳从 aside 换成 .sheet + 两个 .sheet-col
ok('class="sheet m-glass m-glass-strong"' in drawer and 'class="sheet-body"' in drawer,
   "设备详情改成居中弹框")
ok(drawer.count('class="sheet-col"') == 2, "设备详情分左右两列")
ok("<aside" not in drawer, "不再用侧滑抽屉外壳")
for needle in ['aria-modal="true"', 'class="sheet-head"', 'class="sheet-cat mono"']:
    ok(needle in drawer, "弹框骨架 %s" % needle)

# 区块顺序：状态 → 控制 → 历史趋势 → 显示名称 → 自定义分组
# 摄像头专项跟着「控制」走（它本质是取流操作），排在历史趋势之前
SEQUENCE = [
    ("状态", '<label>状态</label>'),
    ("控制", 'dr-section-label">控制'),
    ("摄像头", "<CameraPanel"),
    ("历史趋势", 'dr-section-label">历史趋势'),
    ("显示名称", 'dr-section-label">显示名称'),
    ("自定义分组", 'dr-section-label">自定义分组'),
]
_pos = [drawer.find(anchor) for _, anchor in SEQUENCE]
ok(all(p >= 0 for p in _pos),
   "五个区块都在：" + "、".join(n for n, p in zip([s[0] for s in SEQUENCE], _pos) if p < 0))
ok(_pos == sorted(_pos), "区块顺序为 " + " → ".join(n for n, _ in SEQUENCE))

# 控制 / 历史趋势：没内容就整块不出现，不留「暂无」占位
ok('v-if="hasControls"' in drawer, "控制区按可操作性条件渲染")
ok("d.value.online !== false" in drawer and "(d.value.switches || []).length > 0" in drawer,
   "离线或无可操作项时不显示控制区")
ok('v-if="showHistory"' in drawer, "历史趋势按有无数据条件渲染")
ok("store.historyReady[did.value]" in drawer, "区分「还没拉到」与「确实没采样」")
ok("historyReady" in read(path(SRC, "stores", "devices.ts")),
   "打开弹框时重置该设备的取数标记")
ok("暂无历史数据" not in drawer, "没采样时不再留「暂无历史数据」占位")
ok("设备离线，控制项已隐藏" not in drawer, "离线时不再留控制区空提示")

# 弹窗必须挂在弹框之外：.sheet 带 backdrop-filter，fixed 子元素会相对它定位
ok("<CapDialog" in drawer and drawer.index('class="sheet-body"') < drawer.index("<CapDialog"),
   "取流弹窗挂在遮罩层，不在弹框内容区里")

cap_dlg = read(path(SRC, "components", "CapDialog.vue"))
for needle in ["capDialog(", "cap-layer", "cap-mask", "cap-box", "dialogEnter",
               "dialogLeave", "emit('retry')", "RAW_SUMMARY", "aria-modal",
               "Escape", "m-glass-strong"]:
    ok(needle in cap_dlg, "CapDialog 接线 %s" % needle)
ok("v-html" not in cap_dlg, "弹窗不注入未转义 HTML")
ok("fetch(" not in cap_dlg, "弹窗不绕过数据层直接发请求")
ok(":disabled=\"busy\"" in cap_dlg and "正在检测" in cap_dlg,
   "弹窗内重测期间按钮置灰并给出进行中文案")

detail_ts = text["stores/detail.ts"]
for ep in ["/api/camera/stream", "/api/camera/stop", "/api/camera/action"]:
    ok(ep in detail_ts, "详情数据层覆盖后端端点 %s" % ep)
for needle in ["useDevicesStore", "streams.value",
               "streamNotes.value", "streamBusy.value", "rawText"]:
    ok(needle in detail_ts, "详情数据层具备 %s" % needle)
ok("/api/sched" not in detail_ts and "SchedRule" not in detail_ts,
   "详情数据层不再残留任何定时接口与类型")

# ---- 3. 后端与旧前端零牵连 ----
ok(not os.path.isfile(path(ROOT, "routes", "sched.py")), "后端定时路由已删除")
ok(not os.path.isfile(path(ROOT, "services", "scheduler.py")), "定时调度器已删除")
ok("_bg_loop" in read(path(ROOT, "app.py")), "后台保活循环仍在（刷新设备列表/静默恢复）")
ok("scheduler" not in read(path(ROOT, "app.py")), "启动装配不再引用调度器")
ok(read(path(ROOT, "routes", "camera.py")).find('@bp.route("/api/camera/stream"') >= 0,
   "后端摄像头接口保持原样")
ok("classify" in read(path(ROOT, "static", "camera_panel.js")), "旧摄像头模块仍在")
old_index = read(path(ROOT, "static", "index.html"))
ok("camera_panel.js" in old_index, "旧界面摄像头入口未被删除")
ok("sched-panel" not in old_index and "sched-mask" not in old_index,
   "旧界面定时面板 DOM 已删除")
ok("openSched" not in read(path(ROOT, "static", "app.js")), "旧界面定时交互已删除")
ok("UI_FLAVOR" in read(path(ROOT, "config.py")), "默认入口仍由 UI_FLAVOR 控制")

# ---- 4. 七层样式与语义令牌 ----
styles = ["tokens.css", "base.css", "materials.css", "components.css",
          "instruments.css", "layout.css", "pages.css"]
css = {n: read(path(SRC, "styles", n)) for n in styles}
all_css = "\n".join(css.values())
for legacy in ["var(--card)", "var(--dim)", "var(--text)", "var(--bg)",
               "var(--input)", "var(--radius", "var(--shadow", "var(--off)", "var(--mask)"]:
    ok(legacy not in all_css, "Vue 样式不引用旧界面令牌 %s" % legacy)
for needle in [".cam-video-el", ".cam-placeholder", ".cam-pad-grid",
               ".cam-pad-btn", ".cam-raw pre", ".cam-note"]:
    ok(needle in all_css, "样式钩子 %s 已实装" % needle)
for gone in [".sched-rule", ".sched-add-line", ".day-picker", ".r-time", ".r-meta"]:
    ok(gone not in all_css, "定时样式 %s 已随功能删除" % gone)
ok("position: static" not in css["components.css"], "④ 的旋钮宿主修复未被破坏")
ok(".mini-switch {" in css["components.css"], "mini-switch 基础规则仍在")
ok(".mini-switch::after" in css["components.css"], "开关轨道伪元素仍在")
main_ts = read(path(SRC, "main.ts"))
order = [main_ts.find("styles/%s" % n) for n in styles]
ok(all(i >= 0 for i in order) and order == sorted(order), "七层引入顺序未被打乱")

# ---- 5. 构建产物与文档 ----
ok(os.path.isfile(path(ROOT, "static", "vue", "index.html")), "Vue 构建入口仍在")
ok("/static/vue/assets/" in read(path(ROOT, "static", "vue", "index.html")),
   "产物入口指向 Flask 静态目录")
readme = read(path(ROOT, "README.md"))
ok("⑤ 详情增强" in readme, "README 标注 ⑤ 详情增强")
ok("test_vue_detail.py" in readme, "README 登记新增测试")

print("\n通过 %d 项" % ok_n[0])
