"""样式表不变量：防止「绝对定位子元素失去包含块」这类肉眼才发现的错位。

背景（2026-11-13 修的真实 bug）：头部单键开关为了走流内布局被改成
`position: static`，而开关旋钮是 `.mini-switch::after` 的绝对定位元素。
static 不建立包含块，旋钮于是以整张卡片为参照，跑到卡片左上角，
在 97 张卡片上各画出一个莫名其妙的白圆圈。

这类问题单元测试抓不到、逻辑测试也抓不到，只能靠人盯着截图看——
所以在这里把规则写成断言：只要某选择器有绝对定位的伪元素，
它自己的 position 就绝不能是 static。
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(os.path.dirname(HERE), "static", "style.css")

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


raw = open(CSS_PATH, encoding="utf-8").read()
# 去注释，避免注释里的花括号/分号干扰解析
css = re.sub(r"/\*.*?\*/", "", raw, flags=re.S)


def blocks(text):
    """拆出 [(selector, {prop: value})]，跳过 @media 等嵌套块的内层也能用。"""
    out = []
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        sel = " ".join(m.group(1).split())
        decl = {}
        for part in m.group(2).split(";"):
            if ":" in part:
                k, v = part.split(":", 1)
                decl[k.strip()] = " ".join(v.split())
        if sel:
            out.append((sel, decl))
    return out


BLOCKS = blocks(css)
print("解析规则块：%d 个" % len(BLOCKS))
ok(len(BLOCKS) > 100, "style.css 解析出足够多的规则块")

# ---- 1. 找出所有「绝对定位伪元素」的宿主选择器 ----
ABS_PSEUDO_HOSTS = {}
for sel, decl in BLOCKS:
    if re.search(r"::?(before|after)$", sel) and decl.get("position") == "absolute":
        for host in sel.split(","):
            host = host.strip()
            base = re.sub(r"::?(before|after)$", "", host).strip()
            if base:
                ABS_PSEUDO_HOSTS[base] = host
print("带绝对定位伪元素的宿主：%d 个" % len(ABS_PSEUDO_HOSTS))
ok(".mini-switch" in ABS_PSEUDO_HOSTS, "识别到开关旋钮（.mini-switch::after 绝对定位）")

# ---- 2. 这些宿主的 position 不能是 static ----
def refs_same_element(sel, host):
    """`.mini-switch.in-head` / `.mini-switch:disabled` 都算「同一个元素的变体」。"""
    return sel == host or sel.startswith(host + ".") or sel.startswith(host + ":")


bad = []
for sel, decl in BLOCKS:
    if decl.get("position") != "static":
        continue
    for one in [s.strip() for s in sel.split(",")]:
        for host in ABS_PSEUDO_HOSTS:
            if refs_same_element(one, host):
                bad.append(one)
ok(not bad, "没有宿主被改成 position: static（否则伪元素会跑到祖先元素上）%s"
   % ("" if not bad else "→ " + ", ".join(sorted(set(bad)))))

# ---- 3. 开关的两处摆放都保持流内 + 包含块 ----
pos_map = {}
for sel, decl in BLOCKS:
    for one in [s.strip() for s in sel.split(",")]:
        if "position" in decl:
            pos_map[one] = decl["position"]
ok(pos_map.get(".mini-switch.in-head") == "relative",
   "头部单键开关用 relative 留在流内并建立包含块")
ok(pos_map.get(".sw-row .mini-switch") == "relative",
   "多键开关行内的开关用 relative")
ok(pos_map.get(".mini-switch") == "absolute",
   "开关默认态仍以卡片为参照绝对定位（卡片右上角）")

# ---- 4. 旋钮必须落在胶囊里 ----
sw = dict((s, d) for s, d in BLOCKS if s == ".mini-switch")
knob = dict((s, d) for s, d in BLOCKS if s == ".mini-switch::after")
on_knob = dict((s, d) for s, d in BLOCKS if s == ".mini-switch.on::after")


def px(v, default=0.0):
    m = re.match(r"(-?[\d.]+)px", v or "")
    return float(m.group(1)) if m else default


track_w = px(sw[".mini-switch"].get("width", "0"))
track_h = px(sw[".mini-switch"].get("height", "0"))
knob_w = px(knob[".mini-switch::after"].get("width", "0"))
left_off = px(knob[".mini-switch::after"].get("left", "0"), 3.0)
left_on = px(on_knob[".mini-switch.on::after"].get("left", "0"), 23.0)
top_off = px(knob[".mini-switch::after"].get("top", "0"), 3.0)
ok(knob_w > 0 and track_w > knob_w, "旋钮比胶囊窄")
ok(top_off * 2 + knob_w <= track_h + 0.01, "旋钮竖向不超出胶囊（%.0f+%.0f+%.0f ≤ %.0f）"
   % (top_off, knob_w, top_off, track_h))
ok(left_on + knob_w <= track_w + 0.01, "开启态旋钮不顶出胶囊（%.0f+%.0f ≤ %.0f）"
   % (left_on, knob_w, track_w))
ok(left_off >= 0, "关闭态旋钮不越出胶囊左边界")

# ---- 5. 卡片圆角裁剪不能被去掉 ----
card_decls = [d for s, d in BLOCKS if s == ".device-card"]
ok(any(d.get("overflow") == "hidden" for d in card_decls),
   "卡片仍裁剪溢出内容（旋钮越界时会被切掉而不是画到卡外）")

# ---- 6. 登录页小猫：pico 的 svg fill 规则会吃掉没上色的形状 ----
# pico 里有 `svg:not([fill]){fill:currentColor}`，深色主题下 currentColor 是白的，
# 于是没写 fill 的形状会糊成一片白（真发生过：眼睛变成白球）。两道防线都要在。
cat_css = open(CSS_PATH, encoding="utf-8").read()
svg_decls = [d for s, d in BLOCKS if s == ".lp-cat-svg"]
ok(any(d.get("fill") == "none" for d in svg_decls),
   "小猫 svg 根声明 fill:none（挡住 pico 的当前色填充）")
cat_js = open(os.path.join(os.path.dirname(HERE), "static", "login_cat.js"), encoding="utf-8").read()
ok('class="lp-cat-svg"' in cat_js and 'fill="none"' in cat_js,
   "登录页小猫的 svg 标签自己带 fill=none")
for cls in ("cat-eyeball", "cat-glint", "cat-mouth-sad", "cat-brow"):
    ok(re.search(r"\." + cls + r"(?![-\w])", cat_css) is not None,
       "样式里有 .%s（否则形状透明或染色错）" % cls)

# ---- 7. 情绪钩子：JS 里能给的每种心情都得有样式接手 ----
for mood in ("wait", "ok", "err"):
    ok(re.search(r'\.lp-cat\[data-mood="%s"\]' % mood, cat_css) is not None,
       "有 .lp-cat[data-mood=\"%s\"] 的样式（改心情名不会静默失效）" % mood)

print("\n样式不变量 %d 项全部通过" % ok_n[0])
