#!/usr/bin/env python3
"""Vue 前端主题层不变量：七层顺序、令牌浅深对齐、材质配方、
CSS 预设表与 TS 预设表色值一致、旧 localStorage 键迁移契约。

纯文本静态检查，不需要浏览器；运行时行为另由 headless Chrome 验收。
"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB = os.path.join(ROOT, "web")
STYLES = os.path.join(WEB, "src", "styles")

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


tokens = read(os.path.join(STYLES, "tokens.css"))
base = read(os.path.join(STYLES, "base.css"))
materials = read(os.path.join(STYLES, "materials.css"))
core = read(os.path.join(WEB, "src", "theme", "core.ts"))
store = read(os.path.join(WEB, "src", "stores", "theme.ts"))
main_ts = read(os.path.join(WEB, "src", "main.ts"))
index_html = read(os.path.join(WEB, "index.html"))

LAYERS = ["tokens", "base", "materials", "components", "instruments", "layout", "pages"]

# ---- 1. 七层文件齐全 ----
for name in LAYERS:
    ok(os.path.isfile(os.path.join(STYLES, name + ".css")), "第 %s 层样式文件存在" % name)

# ---- 2. main.ts 按 DESIGN.md 顺序引入 ----
imports = re.findall(r"import '\./styles/(\w+)\.css'", main_ts)
ok(imports == LAYERS, "七层引入顺序与 DESIGN.md 一致 → %s" % " → ".join(imports))
ok("createPinia" in main_ts and "use(createPinia())" in main_ts, "Pinia 已挂到应用")


def decl_keys(block):
    return set(re.findall(r"([\w-]+)\s*:", block))


def css_block(sel, css=tokens):
    """按精确选择器取第一个声明块。"""
    m = re.search(re.escape(sel) + r"\s*\{([^{}]*)\}", css)
    return m.group(1) if m else ""


root_light = css_block(":root")
root_dark = css_block(':root[data-theme="dark"]')
ok(bool(root_light) and bool(root_dark), "令牌层同时定义浅色 :root 与深色 :root[data-theme=\"dark\"]")

light_keys = decl_keys(root_light)
dark_keys = decl_keys(root_dark)
ok(dark_keys <= light_keys, "深色块没有凭空出现浅色未定义的键")
for key in ["--ink", "--ink-muted", "--blue", "--blue-soft", "--stage", "--canvas",
            "--surface", "--line", "--e1", "--e2", "--e3", "--edge", "--rail-bg",
            "--pill-bg", "--float-bg", "--groove-bg", "--input-bg", "--overlay"]:
    ok(key in light_keys and key in dark_keys, "浅/深都定义了 %s" % key)

# ---- 3. 圆角、尺寸、密度三档 ----
for key in ["--r-xs", "--r-sm", "--r-md", "--r-lg", "--r-xl", "--rail-w",
            "--topbar-h", "--control-h", "--row-h", "--cell-px"]:
    ok(key in light_keys, "布局/圆角令牌 %s 存在" % key)
for density, row_h in [("comfy", "56px"), ("compact", "40px")]:
    blk = css_block(':root[data-density="%s"]' % density)
    ok("--row-h: %s" % row_h in blk, "密度 %s 的行高为 %s" % (density, row_h))

# ---- 4. 材质配方与 unslop 视觉不变量 ----
for cls in ["m-rail", "m-pill", "m-float", "m-surface", "m-groove", "m-glow"]:
    ok(("." + cls + " {") in materials or (".m-glow > .glow-layer" in materials and cls == "m-glow"),
       "材质类 .%s 有定义" % cls)
for cls in ["m-rail", "m-pill", "m-float", "m-surface", "m-groove"]:
    blk = css_block("." + cls, materials)
    ok(bool(blk) and "backdrop-filter" not in blk and "linear-gradient(" not in blk,
       ".%s 是实色面，无玻璃模糊与渐变" % cls)
ok("prefers-reduced-transparency" in materials, "降低透明度偏好下有降级")
ok("prefers-reduced-motion" in base, "减少动态效果偏好下有降级")
ok("prefers-reduced-motion" in materials, "指针光在减少动效/粗指针下关闭")

# 九 passes 之后的全局不变量：跨七层一起检查
layers_css = {n: read(os.path.join(STYLES, n + ".css")) for n in LAYERS}
all_css = "\n".join(layers_css.values())
vue_files = sorted(glob.glob(os.path.join(WEB, "src", "components", "*.vue")))
vue_files.append(os.path.join(WEB, "src", "App.vue"))
vue_src = "\n".join(read(p) for p in vue_files)
# 玻璃只允许定义在第 3 层（材质），且只由浮层类使用；其余六层直接引用类名
glass_by_layer = {n: v.count("backdrop-filter") for n, v in layers_css.items()}
ok(glass_by_layer.get("materials", 0) > 0, "浮层玻璃配方落在材质层")
ok(all(c == 0 for n, c in glass_by_layer.items() if n != "materials"),
   "玻璃模糊只在材质层定义，其余六层靠 .m-glass 类使用")
for cls in ["m-glass", "m-glass-strong", "m-glass-rail", "m-glass-menu"]:
    ok(("." + cls) in materials, "材质层提供 .%s" % cls)
ok("--glass-menu" in light_keys and "--glass-menu" in dark_keys,
   "逐行读的菜单另有一档更实的玻璃")
ok(materials.count("backdrop-filter: none") >= 1, "降低透明度偏好下玻璃退回实色")
ok("@supports not ((backdrop-filter" in materials, "不支持模糊时退回实色")
# 四档都必须同时进两条退回路径，否则新加的那一档会在无模糊环境下漏成半透明
for cls in ["m-glass", "m-glass-strong", "m-glass-rail", "m-glass-menu"]:
    ok(materials.count(cls) >= 3, "%s 同时出现在配方、退回与降透明三处" % cls)
for key in ["--glass-bg", "--glass-bg-strong", "--glass-rail", "--glass-head",
            "--glass-hi", "--glass-blur", "--glass-sat"]:
    ok(key in light_keys and key in dark_keys, "浅/深都定义了 %s" % key)
glass_users = re.findall(r'class="[^"]*m-glass[^"]*"', vue_src)
ok(len(glass_users) >= 6, "顶栏、抽屉、下拉、外观面板、提示共用一套玻璃配方")
ok("device-card" not in " ".join(glass_users) and "m-surface m-glass" not in " ".join(glass_users),
   "设备卡片与阅读面板不用玻璃，读数保持实色")
ok("radial-gradient" not in all_css and "mix-blend-mode" not in all_css,
   "没有彩色光晕 / 光斑与混合模式")
ok(all_css.count("linear-gradient(") == all_css.count("repeating-linear-gradient("),
   "唯一的 linear-gradient 是中性斜线填充，没有色相渐变")
ok("--ambient-a: transparent" in tokens and "--ambient-b: transparent" in tokens,
   "环境漫射光令牌已退休")
ok("infinite" not in all_css and "text-transform: uppercase" not in all_css,
   "没有无限循环动效与全大写眉标")
ok(not re.search(r"font-weight:\s*(?:650|700|800|900)", all_css),
   "字重全部落在 400 / 500")
ok("letter-spacing: .14em" not in all_css and "letter-spacing: -.01em" not in all_css,
   "小字没有宽字距或负字距")
ok(all_css.count("999px") == 1, "胶囊只留给开关轨道")
ok(".ui-ico" in layers_css["components"], "统一线性图标类存在")
ok("✕" not in vue_src and "◐" not in vue_src and "▾" not in vue_src,
   "关闭、外观、折叠都换成线性图标")
ok("grain-layer" not in vue_src, "颗粒装饰层已从模板移除")
ok("--ease: cubic-bezier(.22, 1, .36, 1)" in tokens and "--t-fast" in tokens and "--t-slow" in tokens,
   "全站一条缓动曲线、两档时长")
ok("--rail-w: 256px" in tokens and "--topbar-h: 56px" in tokens,
   "侧栏 256 / 顶栏 56 落在桌面应用比例内")

# ---- 5. 七套预设：CSS 与 TS 色值必须一致 ----
ts_entries = re.findall(
    r"\{ id: '(\w+)', name: '([^']+)', hex: '(#[0-9a-fA-F]{6})', darkHex: '(#[0-9a-fA-F]{6})' \}",
    core,
)
ok(len(ts_entries) == 7, "TS 预设表恰好 7 套")
ids = [e[0] for e in ts_entries]
ok(len(set(ids)) == 7, "7 套预设 id 不重复")


def hex_to_rgb_words(h):
    h = h.lstrip("#")
    return "%d %d %d" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


for pid, name, light_hex, dark_hex in ts_entries:
    lb = css_block('html[data-preset="%s"]' % pid)
    db = css_block('html[data-theme="dark"][data-preset="%s"]' % pid)
    ok(bool(lb) and bool(db), "%s（%s）浅/深两套规则都在" % (pid, name))
    ok("--tone: %s" % light_hex in lb, "%s 浅色主色与 TS 一致 %s" % (pid, light_hex))
    ok("--tone: %s" % dark_hex in db, "%s 深色主色与 TS 一致 %s" % (pid, dark_hex))
    ok("--tone-rgb: %s" % hex_to_rgb_words(light_hex) in lb, "%s 浅色 RGB 三元组正确" % pid)
    ok("--tone-rgb: %s" % hex_to_rgb_words(dark_hex) in db, "%s 深色 RGB 三元组正确" % pid)

ok("html[data-preset]:not([data-preset=\"custom\"])" in tokens,
   "存在统一派生规则（非 custom 预设）")
ok('html[data-theme="dark"][data-preset]:not([data-preset="custom"])' in tokens,
   "存在深色统一派生规则（透明度上调）")

# ---- 6. 自定义主色：TS 推导的键与清理清单一致 ----
accent_keys = re.search(r"export const ACCENT_KEYS = \[(.*?)\] as const", core, re.S)
ok(bool(accent_keys), "存在 ACCENT_KEYS 清理清单")
clean_keys = set(re.findall(r"'(--[\w-]+)'", accent_keys.group(1))) if accent_keys else set()
derive = re.search(r"export function deriveAccentVars[\s\S]*?return \{([\s\S]*?)\n  \}", core)
derive_keys = set(re.findall(r"'(--[\w-]+)'\s*:", derive.group(1))) if derive else set()
ok(bool(clean_keys) and bool(derive_keys), "能解析出推导键与清理键")
ok(clean_keys == derive_keys, "推导出的变量全部会被清理（切回预设不残留）%s"
   % ("" if clean_keys == derive_keys else "→ 差集 " + str(clean_keys ^ derive_keys)))
ok("--tone-rgb" in clean_keys and "--blue-soft" in clean_keys, "自定义主色同时驱动新旧两套令牌")

# ---- 7. localStorage 契约与旧键迁移 ----
for key in ["mi-mode", "mi-preset", "mi-accent", "mi-density", "mi-theme"]:
    ok("'%s'" % key in core, "键名 %s 与旧界面一致" % key)
ok("getItem(KEYS.mode) || storage.getItem(KEYS.legacyMode)" in core,
   "readStoredTheme 缺少 mi-mode 时回退旧键 mi-theme")
ok("setItem(KEYS.legacyMode, s.mode)" in core, "persistTheme 回写 mi-theme 供旧界面读取")
ok("ACCENT_RE" in core and "#[0-9a-fA-F]{6}" in core, "自定义主色只接受 6 位 HEX")
ok("watch(state, apply)" in store and "apply()" in store, "store 首帧应用 + 变化自动应用")
for field in ["setMode", "toggleMode", "setPreset", "setAccent", "setDensity", "reset"]:
    ok(("function " + field) in store, "store 暴露 %s()" % field)
ok("dataset.theme" in core and "dataset.preset" in core and "dataset.density" in core,
   "应用函数写入三个 data-* 属性")

# ---- 8. 首帧预涂脚本 ----
inline = re.search(r"<script>([\s\S]*?)</script>", index_html)
ok(bool(inline), "index.html 有内联首帧预涂脚本")
if inline:
    body = inline.group(1)
    for key in ["mi-mode", "mi-theme", "mi-preset", "mi-density"]:
        ok(key in body, "预涂脚本读取 %s" % key)
    for attr in ["dataset.theme", "dataset.preset", "dataset.density"]:
        ok(attr in body, "预涂脚本设置 %s" % attr)

# ---- 9. 旧界面没有被牵连 ----
legacy_index = read(os.path.join(ROOT, "static", "index.html"))
ok("style.css?v=19" in legacy_index, "旧界面入口仍指向 style.css?v=19（未被改动）")
ok("vendor-pico.css" in legacy_index, "旧界面仍加载自己的 Pico 基础样式")
ok("/static/vue/" not in legacy_index, "旧界面没有混入新版资源")

print("\nvue_theme_test: %d 项通过" % ok_n[0])
