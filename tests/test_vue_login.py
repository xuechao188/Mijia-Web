#!/usr/bin/env python3
"""Vue 登录链路（步骤③）不变量。

两类检查：
1) 运行时交叉校验：用 Node 直接加载 TS 纯逻辑（--experimental-strip-types），
   与旧界面 static/login_cat.js 的 svg()/moodOf()/pupilShift()/pickLine()
   逐项比对，并验证登录状态机各分支。
2) 静态文本：端点、文案、轮询节拍、组件接线、样式钩子、旧界面零牵连。
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


cat_ts = read(path(SRC, "login", "cat.ts"))
core_ts = read(path(SRC, "login", "core.ts"))
auth_ts = read(path(SRC, "stores", "auth.ts"))
cat_vue = read(path(SRC, "components", "LoginCat.vue"))
page_vue = read(path(SRC, "components", "LoginPage.vue"))
app_vue = read(path(SRC, "App.vue"))
pages_css = read(path(SRC, "styles", "pages.css"))
app_js = read(path(ROOT, "static", "app.js"))
old_cat = read(path(ROOT, "static", "login_cat.js"))
old_index = read(path(ROOT, "static", "index.html"))
routes_auth = read(path(ROOT, "routes", "auth.py"))

# ---- 1. 文件齐全 ----
for rel in ["login/cat.ts", "login/core.ts", "stores/auth.ts",
            "components/LoginCat.vue", "components/LoginPage.vue"]:
    ok(os.path.isfile(path(SRC, *rel.split("/"))), "新增 %s" % rel)

# ---- 2. 运行时交叉校验（Node 22 strip types） ----
with tempfile.TemporaryDirectory(prefix="vue_login_") as tmp:
    # core.ts 的无扩展名相对导入在 Node ESM 下解不开，测试副本补 .ts 后缀
    open(path(tmp, "cat.ts"), "w", encoding="utf-8").write(cat_ts)
    open(path(tmp, "core.ts"), "w", encoding="utf-8").write(
        core_ts.replace("from './cat'", "from './cat.ts'"))

    probe = r'''
const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
const old = require(process.argv[2]);
const cat = await import('file://' + process.argv[3] + '/cat.ts');
const core = await import('file://' + process.argv[3] + '/core.ts');
const checks = [];
const push = (name, v) => checks.push([name, !!v]);

push('旧界面仍是手绘 SVG 面包猫（新版未覆盖旧文件）',
     typeof old.svg === 'function' && old.svg().indexOf('cat-loaf') >= 0);
push('新版不再内置手绘猫几何', typeof cat.catSvg === 'undefined');
push('眼睛覆盖层 viewBox 与位图同比例',
     cat.CAT_VIEW.w === 664 && cat.CAT_VIEW.h === 860);
push('两只眼睛数量与半径合理',
     cat.CAT_EYES.length === 2 &&
     cat.CAT_EYES.every(e => e.r > 30 && e.r < 60 &&
       e.cx > 0 && e.cx < cat.CAT_VIEW.w && e.cy > 0 && e.cy < cat.CAT_VIEW.h));
push('覆盖层含两个裁剪路径',
     (cat.eyeOverlay().match(/<clipPath /g) || []).length === 2);
push('覆盖层含瞳孔与虹膜渐变',
     cat.eyeOverlay().indexOf('cat-pupil-body') >= 0 &&
     cat.eyeOverlay().indexOf('cat-iris-grad') >= 0);
push('瞳孔位移上限小于眼球半径，不会穿帮',
     cat.PUPIL_MAX < cat.CAT_EYES[0].r * (1 - cat.PUPIL_RX));
push('MOODS 四态与旧版一致', JSON.stringify(old.MOODS) === JSON.stringify(cat.MOODS));
for (const m of ['wait', 'ok', 'err']) {
  push('LINES(' + m + ') 与旧版一致',
       JSON.stringify(old.LINES[m]) === JSON.stringify(cat.LINES[m]));
}
push('LINES(idle) 前四句与旧版一致',
     JSON.stringify(old.LINES.idle.slice(0, 4)) === JSON.stringify(cat.LINES.idle.slice(0, 4)));
push('idle 末句随猫的品种更新为橘猫',
     cat.LINES.idle[4] === '橘猫已就位');

const moods = [
  ['正在获取二维码…', ''], ['请使用米家 App 扫码', ''],
  ['登录成功，正在进入…', 'ok'], ['二维码已过期', 'err'],
  ['扫码登录出错', 'err'], ['正在恢复登录（等待小米风控解除）…', ''],
  ['网络异常，稍后重试', 'err'], ['', ''], [null, 'ok'],
];
for (const [t, c] of moods) {
  push('moodOf(' + String(t) + '/' + c + ') 与旧版一致',
       old.moodOf(t, c) === cat.moodOf(t, c) && cat.moodOf(t, c) === core.moodForStatus(t, c));
}
for (const [mx, my, cx, cy, max] of [
  [0, 0, 100, 100, 2.4], [101, 100, 100, 100, 2.4], [300, 20, 100, 100, 2.6],
  [NaN, 3, 1, 2, 2.4], [10, 10, 10, 10, 0],
]) {
  const a = old.pupilShift(mx, my, cx, cy, max), b = cat.pupilShift(mx, my, cx, cy, max);
  push('pupilShift(' + [mx, my, cx, cy, max] + ') 与旧版一致',
       a.x === b.x && a.y === b.y);
}
for (const m of old.MOODS) {
  for (let n = -5; n <= 12; n++) {
    // idle 第 5 句已随品种更新，其余逐项对齐旧版
    if (m === 'idle' && Math.abs(n) % 5 === 4) continue;
    push('pickLine(' + m + ',' + n + ') 与旧版一致', old.pickLine(m, n) === cat.pickLine(m, n));
  }
}

const polls = [
  [{ status: 'waiting' }, 'waiting', '请使用米家 App 扫码', '', false, ''],
  [{ status: 'ok' }, 'ok', '登录成功，正在进入…', 'ok', true, ''],
  [{ logged_in: true }, 'ok', '登录成功，正在进入…', 'ok', true, ''],
  [{ restoring: true }, 'restoring', '正在恢复登录（等待小米风控解除）…', '', false, ''],
  [{ status: 'expired' }, 'expired', '二维码已过期', 'err', true, '二维码已过期'],
  [{ status: 'error', error: '风控拦截' }, 'error', '风控拦截', 'err', true, '出错了'],
  [{ status: 'error' }, 'error', '扫码登录出错', 'err', true, '出错了'],
  [{}, 'idle', '请使用米家 App 扫码', '', false, ''],
  [null, 'idle', '请使用米家 App 扫码', '', false, ''],
];
for (const [r, act, text, cls, stop, overlay] of polls) {
  push('classifyPoll(' + JSON.stringify(r) + ') → ' + act, core.classifyPoll(r) === act);
  const s = core.statusFor(act, r && r.error);
  push('statusFor(' + act + ') 文案/类/停轮询/遮罩一致',
       s.text === text && s.cls === cls && s.stop === stop && s.overlay === overlay);
}

for (const [r, want] of [
  [{ logged_in: true }, 'logged'], [{ logged_in: false, restoring: false }, 'show'],
  [{ logged_in: false, restoring: true }, 'wait'], [null, 'wait'], [{}, 'show'],
]) {
  push('restoreDecision(' + JSON.stringify(r) + ') → ' + want,
       core.restoreDecision(r) === want);
}
for (const [r, ok_, already, cls] of [
  [{ ok: true }, true, false, ''],
  [{ ok: false, error: '已登录' }, false, true, 'ok'],
  [{ ok: false, error: '二维码获取失败' }, false, false, 'err'],
  [{ ok: false }, false, false, 'err'],
]) {
  const v = core.classifyStart(r);
  push('classifyStart(' + JSON.stringify(r) + ') 一致',
       v.ok === ok_ && v.already === already && v.cls === cls);
}
push('QR_POLL_MS = 2500', core.QR_POLL_MS === 2500);
push('RESTORE_STEP_MS = 500', core.RESTORE_STEP_MS === 500);
push('RESTORE_MAX_TRIES = 12', core.RESTORE_MAX_TRIES === 12);
push('LOGIN_HOP_MS = 700', core.LOGIN_HOP_MS === 700);
console.log(JSON.stringify(checks));
'''
    probe_path = path(tmp, "probe.mjs")
    open(probe_path, "w", encoding="utf-8").write(probe)
    proc = subprocess.run(
        ["node", "--experimental-strip-types", probe_path,
         path(ROOT, "static", "login_cat.js"), tmp],
        cwd=ROOT, capture_output=True, text=True, timeout=90,
    )
    ok(proc.returncode == 0, "Node 能加载 TS 纯逻辑并与旧版比对%s"
       % ("" if proc.returncode == 0 else " → " + proc.stderr[-300:]))
    if proc.returncode == 0:
        for name, passed in json.loads(proc.stdout.strip().splitlines()[-1]):
            ok(passed, name)

# ---- 3. 端点对齐后端 ----
ENDPOINTS = ["/api/status", "/api/login", "/api/otp", "/api/logout",
             "/api/login/qr/start", "/api/login/qr/image", "/api/login/qr/poll"]
for ep in ENDPOINTS:
    ok(ep in auth_ts, "新版调用 %s" % ep)
    ok('@bp.route("%s"' % ep in routes_auth, "后端已实现 %s" % ep)
new_eps = set(e.split("?")[0] for e in
              re.findall(r"['\"](/api/[^'\"]+)['\"]", auth_ts))
ok(new_eps <= set(ENDPOINTS), "新版没有调用后端不存在的登录端点 → %s" % sorted(new_eps))
ok("QR_POLL_MS" in auth_ts and "setInterval(pollQr" in auth_ts,
   "二维码轮询用 2.5 秒常量驱动")
ok("RESTORE_MAX_TRIES" in auth_ts and "RESTORE_STEP_MS" in auth_ts,
   "恢复检查用 12 × 500ms 常量驱动")
ok("apiPost<" in auth_ts and "method: 'POST'" in auth_ts, "POST 走 JSON body，与旧 api() 一致")

# ---- 4. 文案与旧版一致 ----
for text in ["正在获取二维码…", "请使用米家 App 扫码", "登录成功，正在进入…",
             "正在恢复登录（等待小米风控解除）…", "二维码已过期", "扫码登录出错",
             "二维码获取失败", "网络异常，稍后重试", "正在检查登录状态…"]:
    ok(text in core_ts, "QR_TEXT 收录「%s」" % text)
    ok(text in app_js or text in old_index, "「%s」在旧版有出处" % text)
ok("请填写账号和密码" in auth_ts and "验证码已提交，请稍候再刷新" in auth_ts,
   "密码 / 验证码文案与旧版一致")

# ---- 5. 状态机接线 ----
for token in ["stopQrPoll", "setQrStatus", "showOverlay", "setTab", "onLoginSuccess",
              "finishEnter", "passwordLogin", "submitOtp", "logout", "bootstrap",
              "waitForRestore", "startQr", "pollQr", "destroy"]:
    ok("function %s(" % token in auth_ts, "auth store 提供 %s()" % token)
ok("phase.value = 'entering'" in auth_ts and "phase.value = 'app'" in auth_ts,
   "登录成功先进 entering 再由猫回调进 app")
ok("setTimeout" not in auth_ts.split("function onLoginSuccess")[1].split("function finishEnter")[0],
   "onLoginSuccess 不自己起收页定时器（由猫 playIn 持有）")
ok("clearInterval(pollTimer)" in auth_ts, "停轮询会清掉 interval")
ok("phase.value = 'login'" in auth_ts.split("async function logout")[1],
   "退出登录回到 login 态（由 LoginPage 的 phase 监听重取码）")
ok("startQr()" not in auth_ts.split("async function logout")[1].split("function destroy")[0],
   "退出登录不重复发两次 /qr/start")

# ---- 6. 登录页组件 ----
for token in ['auth.setTab(\'qr\')', 'auth.setTab(\'pwd\')', 'auth.qrSrc', 'auth.overlay',
              'auth.qrText', 'auth.qrCls', 'auth.loginMsg', 'auth.otpVisible',
              'auth.mood', 'auth.hopMs', 'auth.finishEnter']:
    ok(token in page_vue, "LoginPage 接线 %s" % token)
ok("ref=\"cat\"" in page_vue and ":mood=\"auth.mood\"" in page_vue, "猫挂在登录卡片底部、心情由 store 驱动")
ok("playIn(auth.hopMs, done)" in page_vue, "登录成功由猫 playIn 收页")
ok("@click=\"auth.startQr()\"" in page_vue, "遮罩刷新按钮重取二维码")
ok("theme.toggleMode()" in page_vue, "右上角外观按钮接主题 store")
ok("autocomplete=\"username\"" in page_vue and "autocomplete=\"current-password\"" in page_vue,
   "密码页签保留浏览器自动填充")
ok("@keyup.enter=\"onLogin\"" in page_vue, "密码框回车提交")

# ---- 7. 猫组件 ----
ok("v-html=\"eyesMarkup\"" in cat_vue, "猫用 v-html 渲染眼睛覆盖层")
ok("lp-cat-photo" in cat_vue and "cat-orange" in cat_vue, "猫体是 3D 位图资源")
ok("defineExpose({ say, poke, playIn })" in cat_vue, "对外暴露 say / poke / playIn")
ok("requestAnimationFrame" in cat_vue and "getBoundingClientRect" in cat_vue,
   "瞳孔跟随用 rAF 节流")
ok("--px" in cat_vue and "--py" in cat_vue, "瞳孔位移写 CSS 变量")
ok("classList.remove('is-poked')" in cat_vue and "void el.offsetWidth" in cat_vue,
   "点猫强制重排以重播抖尾动画")
ok("removeEventListener('mousemove'" in cat_vue, "卸载时摘掉全局监听")
ok("if (going)" in cat_vue, "playIn 只跳一次，重复回调直接放行")
for mood in ["idle", "wait", "ok", "err"]:
    ok(':data-mood="current"' in cat_vue and mood in cat_ts, "四态 %s 有纯逻辑来源" % mood)

# ---- 8. 样式层 ----
for sel in [".login-stage", ".lp-card", ".lp-mode", ".lp-tabs", ".lp-tab.active",
            ".qr-frame", ".qr-placeholder", ".qr-overlay", ".qr-status.ok", ".qr-status.err",
            ".lp-pwd input", ".lp-login-btn", ".otp-box", ".lp-cat", ".lp-cat-art",
            ".lp-cat-photo", ".lp-cat-eyes", ".cat-pupil", ".cat-lid", ".cat-droop",
            ".cat-say.show"]:
    ok(sel in pages_css, "pages.css 定义 %s" % sel)
ok(".lp-shell" in pages_css and ".lp-cat-side" in pages_css, "登录页是左猫右卡的左右布局")
for mood in ["idle", "wait", "ok", "err"]:
    ok('.lp-cat[data-mood="%s"]' % mood in pages_css or mood == "idle",
       "第 7 层有 %s 心情样式钩子" % mood)
for key in ["cat-hop", "cat-blink", "cat-pupil", "prefers-reduced-motion", "is-poked"]:
    ok(key in pages_css, "猫一次性状态动作 / 降级规则含 %s" % key)
ok("background: #fff" in pages_css, "二维码底板在深色主题下仍为纯白")
ok(':root[data-theme="dark"] .qr-overlay' in pages_css, "深色主题遮罩有专属配色")
ok("html[data-theme=\"dark\"] .lp-cat" in pages_css, "深色主题猫毛色有覆盖")
for token in ["var(--surface)", "var(--glass-line)", "var(--e3)", "var(--blue)",
              "var(--ink-faint)", "var(--r-xl)", "var(--focus)"]:
    ok(token in pages_css, "登录页使用设计令牌 %s" % token)
for legacy in ["var(--card)", "var(--accent)", "var(--accent-strong)", "var(--dim)",
               "var(--text)", "var(--shadow-sm)", "var(--input)"]:
    ok(legacy not in pages_css, "pages.css 不残留旧令牌 %s" % legacy)

# ---- 9. App 编排与旧界面零牵连 ----
ok("<LoginPage v-if=\"auth.phase !== 'app'\"" in app_vue, "未登录时登录页是唯一内容")
ok("await auth.bootstrap()" in app_vue, "启动先跑恢复检查")
ok("@click=\"auth.logout()\"" in app_vue, "主界面占位提供退出登录")
ok('class="steps' not in app_vue, "页面底部不再挂迁移进度条")
ok("login_cat.js" in old_index and "lp-cat-host" in old_index,
   "旧界面登录猫仍在（新版不覆盖旧文件）")
ok("setQrStatus" in app_js and "LoginCat.moodOf" in app_js,
   "旧界面状态机未被改动")
ok("2.5" not in core_ts, "轮询节拍写成常量而非魔法数字字符串")

print("\nVue 登录链路 %d 项全部通过" % ok_n[0])
