#!/usr/bin/env python3
"""Vue 前端动效层不变量：GSAP 只从 motion 目录进出、四种语态参数、
prefers-reduced-motion 一律进终态、页面/抽屉/卡片/读数/主题的接线。

纯文本静态检查 + 一次 Node 运行时读 VOICE 真实值；视觉效果由
headless Chrome 验收，本文件只管「结构没被绕过」。
"""
import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
SRC = os.path.join(WEB, "src")
MOTION = os.path.join(SRC, "motion")

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


voice = read(path(MOTION, "voice.ts"))
motion = read(path(MOTION, "index.ts"))
countup = read(path(MOTION, "countup.ts"))
app = read(path(SRC, "App.vue"))
grid = read(path(SRC, "components", "DeviceGrid.vue"))
card = read(path(SRC, "components", "DeviceCard.vue"))
drawer = read(path(SRC, "components", "DeviceDrawer.vue"))
pkg = read(path(WEB, "package.json"))
materials = read(path(SRC, "styles", "materials.css"))
layout = read(path(SRC, "styles", "layout.css"))

# ---- 1. 依赖与唯一入口 ----
ok(re.search(r'"gsap"\s*:\s*"\^?3\.', pkg) is not None, "package.json 依赖 GSAP 3")
for name in ["voice.ts", "index.ts", "countup.ts"]:
    ok(os.path.isfile(path(MOTION, name)), "动效层文件 %s" % name)

# 除了 motion 目录，任何组件都不许直接 import gsap
outside = []
for base, _dirs, files in os.walk(SRC):
    if os.path.abspath(base).startswith(os.path.abspath(MOTION)):
        continue
    for fn in files:
        if fn.endswith((".ts", ".vue")):
            body = read(path(base, fn))
            if re.search(r"from\s+['\"]gsap['\"]", body):
                outside.append(fn)
ok(outside == [], "gsap 只在 motion/ 里 import（越界：%s）" % (outside or "无"))
ok(motion.count("from 'gsap'") == 1, "动效层只有一处 gsap 依赖")

# ---- 2. 四种语态 ----
for name, cn in [("release", "放"), ("guide", "导"), ("settle", "结"), ("stall", "停摆")]:
    ok(name in voice, "语态 %s（%s）已定义" % (name, cn))
ok(all(cn in voice for cn in ["放", "导", "结", "停摆"]), "语态表注释写明四种语义")

# Node 真实读一遍参数，避免只在注释里存在
probe = """
const { VOICE } = await import(process.argv[2]);
const checks = [];
const need = ['release', 'guide', 'settle', 'stall'];
for (const k of need) checks.push([k, !!VOICE[k] && typeof VOICE[k].dur === 'number' && typeof VOICE[k].ease === 'string']);
checks.push(['range', ['release', 'guide', 'settle'].every((k) => VOICE[k].dur >= 0.15 && VOICE[k].dur <= 0.6)]);
checks.push(['stagger', VOICE.release.stagger > 0 && VOICE.release.stagger < 0.05]);
checks.push(['rise', VOICE.release.rise > 0 && VOICE.release.scale > 0.9 && VOICE.release.scale < 1]);
checks.push(['order', VOICE.guide.dur < VOICE.release.dur && VOICE.settle.dur < VOICE.release.dur]);
checks.push(['stallSlow', VOICE.stall.dur > 1.5]);
const fail = checks.filter(([, v]) => !v).map(([n]) => n);
console.log(JSON.stringify({ total: checks.length, fail, voice: VOICE }));
if (fail.length) process.exit(1);
"""
with tempfile.TemporaryDirectory() as tmp:
    probe_path = path(tmp, "voice_probe.mjs")
    open(probe_path, "w", encoding="utf-8").write(probe)
    proc = subprocess.run(
        ["node", "--experimental-strip-types", probe_path,
         "file://" + path(MOTION, "voice.ts")],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
        sys.exit(1)
    payload = {}
    for line in proc.stdout.strip().splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
    ok(payload.get("fail") == [], "Node 读到的四语态参数全过 %s 项" % payload.get("total", 0))
    for _ in range(int(payload.get("total", 0))):
        ok_n[0] += 1
    v = payload.get("voice", {})
    ok(abs(float(v.get("release", {}).get("dur", 0)) - 0.38) < 1e-6, "放 0.38s（唯一来源）")
    ok(abs(float(v.get("guide", {}).get("dur", 0)) - 0.18) < 1e-6, "导 0.18s（切页要快）")

# ---- 3. 减弱动效：一处判断，全站进终态 ----
ok("prefers-reduced-motion: reduce" in motion, "监听系统的减弱动效偏好")
ok("addEventListener('change'" in motion and "addListener" in motion, "新旧浏览器都挂得上监听")
ok("export function motionOff" in motion, "对外暴露 motionOff()")
ok(motion.count("motionOff()") >= 8, "每个动效出口都先问 motionOff")
ok("if (motionOff()) { done(); return }" in motion, "转场在减弱动效下同步收尾")
ok("typeof document === 'undefined'" in motion, "无 DOM 的 Node 探针里也不炸")
ok("setTimeout(fin" in motion, "Transition 的 done 有兜底，不会把页面卡在离场")

# ---- 4. 外壳接线：页面转场、主题扫光、抽屉 ----
ok(app.count(':css="false"') == 3, "页面与两个抽屉都用 JS 驱动的 Transition")
ok('mode="out-in"' in app and "@enter=\"pageEnter\"" in app and "@leave=\"pageLeave\"" in app,
   "主标签页切换走 pageEnter/pageLeave")
for key in ["devices", "scenes", "automations", "notices", "logs"]:
    ok('key="%s"' % key in app, "面板分支 %s 有稳定 key" % key)
ok("themeSweep(" in app and "--stage" in app, "主题切换读新底色做一次扫光")
ok("breathe(pingEl.value" in app, "后端未连通时状态点呼吸")
ok('ref="pingEl"' in app, "呼吸作用在状态点本身")
ok("onDrawerEnter" in app and "onDrawerLeave" in app, "自动化/天气抽屉交给动效层")
ok(app.count('<Transition :css="false"') == 3, "三个浮层各有一段 Transition")

# ---- 5. 网格：入场、FLIP、停摆 ----
ok("releaseCards(gridEl.value" in grid, "网格挂载后播放入场")
ok("store.filter, store.home, store.kw" in grid, "换家庭/筛选/搜索时整批重播")
ok("cards.value.length" in grid, "轮询新增设备只补播自己")
ok("captureRects(gridEl.value)" in grid and "flipCards(" in grid, "拖拽换序按矩形差补位")
# 停摆语态只剩顶栏状态点：底部铭牌条已拆，别再把呼吸挂到不存在的节点
ok("breathe(lampEl.value" not in app and "lampEl" not in app, "铭牌灯呼吸随铭牌一起删除")
ok("breathe(statEl.value" not in grid, "统计板本身不做呼吸")
ok('ref="gridEl"' in grid, "网格 ref 绑到真实节点")
ok('ref="plate-bar' not in app and "plate-bar" not in app, "底栏整条移除")

# ---- 6. 读数滚动 ----
ok("import { vCount }" in card and "v-count" in card, "卡片读数走 v-count")
ok("import { vCount }" in drawer and "v-count" in drawer, "抽屉读数走 v-count")
ok("el.dataset.countText" in countup, "指令记住上一次的文本")
ok("prev.replace(a[0], '#') !== next.replace(b[0], '#')" in countup, "格式变了不滚动（开→关不演数字）")
ok("toFixed(digits)" in countup, "滚动过程保留原小数位")
ok("el.textContent = next" in countup, "动画结束回写模板真值")
ok("overwrite: true" in countup, "连续更新不叠加两条补间")

# ---- 7. 弹框模板 ----
ok('<Transition :css="false" @enter="onEnter" @leave="onLeave">' in drawer, "设备弹框也用同一套进出")
ok("drawerEnter(" in drawer and "drawerLeave(" in drawer, "弹框动效来自统一入口")
ok('class="sheet m-glass m-glass-strong"' in drawer, "动效作用在居中弹框上")
ok("x: 40" not in motion and "y: 12, scale: 0.985" in motion,
   "弹框从下方微缩抬升，不再从右侧滑入")

# ---- 7b. 场景砖：按下水波、成功落脚 ----
scenes_vue = read(path(SRC, "components", "ScenesPanel.vue"))
for needle in ["scenePress(", "sceneSettle(", "@pointerdown", 'class="st-ico"',
               'class="st-spin"', "spin("]:
    ok(needle in scenes_vue, "场景砖接线 %s" % needle)
ok("const r = Math.max(" in motion and "Math.hypot(w - x, h - y)" in motion,
   "水波半径取到最远角，圆能盖满整块砖（不露弧形切边）")
ok("host.style.removeProperty('transform')" in motion,
   "落脚后清掉内联 transform，hover 上浮不会被压住")
ok("gsap.timeline({ onComplete: () => rip.remove() })" in motion, "水波播完自己回收")
ok("export function spin(el: Element | null, on: boolean)" in motion,
   "执行中转圈由动效层负责，不在 CSS 里写 infinite")
ok("repeat: -1, ease: 'none'" in motion, "转圈匀速、只随 busy 存续")
ok("'transform', 'translate', 'rotate', 'scale', 'transform-origin'" in motion,
   "停转后把内联变换与原点一起清掉")
ok(motion.count("if (!el || motionOff()) return") >= 2, "场景动效同样尊重减弱动效")

# ---- 8. 样式配合 ----
veil = re.search(r"\.theme-veil\s*\{([^}]*)\}", materials)
ok(bool(veil), "材质层有主题扫光遮罩")
if veil:
    body = veil.group(1)
    ok("position: fixed" in body and "inset: 0" in body, "扫光铺满视口")
    ok("pointer-events: none" in body, "扫光不拦点击")
    ok("--layer-toast" in body, "扫光层级压在内容之上")
sheet_rule = re.search(r"\n\.sheet\s*\{([^}]*)\}", layout)
ok(bool(sheet_rule) and "animation:" not in sheet_rule.group(1), "弹框不再自己播 CSS 动画")
ok("@keyframes drawer-in" not in layout, "旧的 drawer-in 已删，避免两套位移叠加")

# ---- 9. 文档 ----
readme = read(path(ROOT, "README.md"))
ok("GSAP" in readme, "README 记录动效层")

print("\nvue_motion_test: %d 项通过" % ok_n[0])
