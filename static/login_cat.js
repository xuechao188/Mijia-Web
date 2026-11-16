/* 登录页的小猫：一只 loaf 面包猫，坐在登录卡片底部。
 *
 * 它不需要喂食，但会看人：鼠标在页面上移动时瞳孔跟着走；
 * 切到「等你扫码」会坐起来甩尾巴；扫码成功会跳一下再送你进门；
 * 二维码过期就垂耳朵。点它就喵一句。
 *
 * 浏览器里挂 window.LoginCat，app.js 调：
 *   LoginCat.install({ mount, onLine })
 *   LoginCat.setMood(LoginCat.moodOf(text, cls))   // 由 setQrStatus 驱动
 *   LoginCat.playIn(ms, done)                      // 登录成功：跳一下再进主页
 * Node 里可直接 require 测纯函数（moodOf / pupilShift / pickLine / svg）。
 */
(function (root) {
  "use strict";

  var MOODS = ["idle", "wait", "ok", "err"];

  /* 二维码状态文案 → 猫的心情。
   * 文案来自 app.js 的 setQrStatus，这里只做语义归类，不反向依赖。 */
  function moodOf(text, cls) {
    var t = String(text == null ? "" : text);
    if (cls === "ok") return "ok";
    if (cls === "err") return "err";
    if (t.indexOf("成功") >= 0) return "ok";
    if (t.indexOf("过期") >= 0 || t.indexOf("失败") >= 0 || t.indexOf("出错") >= 0) return "err";
    if (t.indexOf("扫码") >= 0) return "wait";      // 请使用米家 App 扫码
    return "idle";                                   // 取二维码 / 恢复登录 / 检查状态
  }

  /* 瞳孔跟随：把「眼睛中心 → 鼠标」的位移缩放到瞳孔最大偏移内。
   * 只取前 6 倍半径的信号，鼠标离得远也不会把瞳孔顶到眼白外面。 */
  function pupilShift(mx, my, cx, cy, max) {
    var m = typeof max === "number" && max > 0 ? max : 2.4;
    var dx = Number(mx) - Number(cx);
    var dy = Number(my) - Number(cy);
    if (!isFinite(dx) || !isFinite(dy)) return { x: 0, y: 0 };
    var d = Math.sqrt(dx * dx + dy * dy);
    if (!d) return { x: 0, y: 0 };
    var k = Math.min(1, d / 220);          // 距离增益：近处细跟、远处封顶
    var r = Math.min(m, d * k * 0.12);
    return {
      x: Math.round((dx / d) * r * 100) / 100,
      y: Math.round((dy / d) * r * 100) / 100,
    };
  }

  /* 点猫时的台词：按心情分组，同一心情下轮着说，不会连着重复。 */
  var LINES = {
    idle: ["喵", "我在呢", "慢慢来，不着急", "今天想看哪台设备", "面包猫已就位"],
    wait: ["扫一下就好", "我盯着二维码呢", "手机在手上吗", "别急，我等你"],
    ok: ["喵！进去啦", "欢迎回来", "门开着呢"],
    err: ["唔…码过期了", "再来一次吧", "这次没扫上"],
  };

  function pickLine(mood, n) {
    var list = LINES[mood] || LINES.idle;
    var i = Math.abs(parseInt(n, 10) || 0) % list.length;
    return list[i];
  }

  /* ---- 猫本体：一只 loaf 面包猫，头在左、身体在右、尾巴在右后方 ----
   * 所有颜色走 CSS 变量，浅色/深色主题共用一套几何。 */
  function svg() {
    return '' +
    '<svg class="lp-cat-svg" viewBox="0 0 200 120" fill="none" role="img" aria-label="登录页的小猫" focusable="false">' +
      '<ellipse class="cat-shadow" cx="106" cy="112" rx="54" ry="6"/>' +
      // 尾巴：从身体右后方探出来，绕根部摆动
      '<g class="cat-tail">' +
        '<path class="cat-tail-fur" d="M150 98c18 3 29-4 31-14 1-7-3-11-8-10-4 1-5 5-2 7"/>' +
      '</g>' +
      // 身体：面包形（loaf）——猫把自己收成一个椭圆蹲着，前爪收在下巴前
      '<g class="cat-body">' +
        '<path class="cat-loaf" d="M62 105c-11 0-18-7-18-15 0-9 9-15 27-15h59c19 0 30 7 30 16 0 9-8 14-18 14z"/>' +
        '<g class="cat-stripes">' +
          '<path d="M100 81c-3-3.4-6.4-4.6-10-4.6M118 80c-2.4-3.2-5.4-4.4-8.4-4.4"/>' +
        '</g>' +
        '<g class="cat-paws">' +
          '<ellipse class="cat-paw" cx="80" cy="102" rx="10" ry="6"/>' +
          '<ellipse class="cat-paw" cx="102" cy="102" rx="10" ry="6"/>' +
          '<path class="cat-toe" d="M76 106v-4M81 106v-4M98 106v-4M103 106v-4"/>' +
        '</g>' +
      '</g>' +
      // 头：两只大三角耳 + 大圆脸，耳朵在前脸之前先画（压在头后面）
      '<g class="cat-head">' +
        '<g class="cat-ear ear-l">' +
          '<path class="cat-ear-fur" d="M55 43 45 11 77 32Z"/>' +
          '<path class="cat-ear-in" d="M57 34 52 18 69 27Z"/>' +
        '</g>' +
        '<g class="cat-ear ear-r">' +
          '<path class="cat-ear-fur" d="M79 32 109 11 99 43Z"/>' +
          '<path class="cat-ear-in" d="M86 28 101 20 99 33Z"/>' +
        '</g>' +
        '<circle class="cat-face" cx="76" cy="58" r="30"/><path class="cat-tuft" d="M77 29c-1.4-5 0-8.6 3.4-10.4-2 3.2-1 6.2 1.4 8.2"/>' +
        '<g class="cat-eyes">' +
          '<g class="cat-eye eye-l"><ellipse class="cat-eyeball" cx="66" cy="56" rx="5.4" ry="6.2"/>' +
            '<circle class="cat-glint" cx="68" cy="53.6" r="1.7"/></g>' +
          '<g class="cat-eye eye-r"><ellipse class="cat-eyeball" cx="86" cy="56" rx="5.4" ry="6.2"/>' +
            '<circle class="cat-glint" cx="88" cy="53.6" r="1.7"/></g>' +
          '<path class="eye-happy" d="M60 57c2-5 9-5 11 0M81 57c2-5 9-5 11 0"/>' +
        '</g>' +
        '<ellipse class="cat-blush" cx="54" cy="70" rx="7" ry="3.6"/>' +
        '<ellipse class="cat-blush" cx="98" cy="70" rx="7" ry="3.6"/>' +
        '<path class="cat-nose" d="M72 65h8l-4 5z"/>' +
        '<path class="cat-mouth" d="M76 70c0 3.4-4.4 4.4-6.6 2.2M76 70c0 3.4 4.4 4.4 6.6 2.2"/>' +
        /* 失落态专用：眉尾下垂 + 嘴朝下，默认透明，靠 data-mood="err" 显形 */
        '<g class="cat-sad">' +
          '<path class="cat-brow" d="M61 47.6l9-2.6M91 47.6l-9-2.6"/>' +
          '<path class="cat-mouth-sad" d="M70 75.2q6-4.8 12 0"/>' +
        '</g>' +
        '<g class="cat-whiskers">' +
          '<path d="M58 63 41 58M58 67 39 67M58 71 42 77M94 63 111 58M94 67 113 67M94 71 110 77"/>' +
        '</g>' +
      '</g>' +
    '</svg>';
  }

  var DEPS = {};
  var el = null;          // 根容器
  var bubble = null;      // 气泡
  var svgEl = null;       // <svg>
  var lineN = 0;
  var sayTimer = null;
  var hopTimer = null;
  var going = false;      // playIn 只生效一次，避免重复登录回调叠加延迟
  var raf = 0;

  function install(deps) {
    DEPS = deps || {};
    var mount = DEPS.mount;
    if (!mount) return API;
    el = mount;
    el.classList.add("lp-cat");
    el.dataset.mood = "idle";
    el.innerHTML = svg() +
      '<div class="cat-say" role="status" aria-live="polite"></div>' +
      '<div class="cat-hint" aria-hidden="true">点我</div>';
    bubble = el.querySelector(".cat-say");
    svgEl = el.querySelector(".lp-cat-svg");
    el.addEventListener("click", poke);
    el.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); poke(); }
    });
    el.tabIndex = 0;
    el.setAttribute("role", "img");
    el.setAttribute("title", "点一下");
    bindEyes();
    return API;
  }

  /* 瞳孔跟随：rAF 节流，只改两个 CSS 变量 */
  function bindEyes() {
    if (typeof window === "undefined" || !svgEl) return;
    var eyes = svgEl.querySelector(".cat-eyes");
    if (!eyes) return;
    var queued = false, last = null;
    window.addEventListener("mousemove", function (e) {
      last = e;
      if (queued) return;
      queued = true;
      raf = window.requestAnimationFrame(function () {
        queued = false;
        if (!last || el.dataset.mood === "ok") return;
        var r = eyes.getBoundingClientRect();
        var s = pupilShift(last.clientX, last.clientY,
                           r.left + r.width / 2, r.top + r.height / 2, 2.6);
        el.style.setProperty("--px", s.x + "px");
        el.style.setProperty("--py", s.y + "px");
      });
    }, { passive: true });
  }

  function setMood(mood) {
    if (!el) return;
    var m = MOODS.indexOf(mood) >= 0 ? mood : "idle";
    if (el.dataset.mood === m) return;
    el.dataset.mood = m;
    if (m === "ok" || m === "err") el.classList.remove("is-poked");
  }

  /* 说一句：ms 后自动收起，期间再点会换一句并重新计时 */
  function say(text, ms) {
    if (!bubble) return null;
    bubble.textContent = String(text || "");
    bubble.classList.add("show");
    if (sayTimer) clearTimeout(sayTimer);
    sayTimer = setTimeout(function () {
      bubble.classList.remove("show");
      sayTimer = null;
    }, ms || 1900);
    return bubble.textContent;
  }

  function poke() {
    var mood = (el && el.dataset.mood) || "idle";
    lineN++;
    var text = pickLine(mood, lineN);
    if (el) {
      el.classList.remove("is-poked");
      void el.offsetWidth;            // 重排一次，让抖尾动画能重播
      el.classList.add("is-poked");
    }
    say(text, 1800);
    if (DEPS.onLine) DEPS.onLine(text);
    return text;
  }

  /* 登录成功：先跳一下，再让调用方收页。
   * 只跳一次；重复调用直接走 done，避免卡在登录页。 */
  function playIn(ms, done) {
    var wait = typeof ms === "number" && ms >= 0 ? ms : 700;
    if (going) { if (done) done(); return; }
    going = true;
    setMood("ok");
    say(pickLine("ok", 0), wait);
    hopTimer = setTimeout(function () {
      hopTimer = null;
      if (done) done();
    }, wait);
    return wait;
  }

  /* 测试/调试用：清掉所有定时器与状态 */
  function reset() {
    if (sayTimer) clearTimeout(sayTimer);
    if (hopTimer) clearTimeout(hopTimer);
    if (raf && typeof window !== "undefined") window.cancelAnimationFrame(raf);
    sayTimer = hopTimer = raf = null;
    going = false;
    lineN = 0;
  }

  var API = {
    MOODS: MOODS,
    LINES: LINES,
    moodOf: moodOf,
    pupilShift: pupilShift,
    pickLine: pickLine,
    svg: svg,
    install: install,
    setMood: setMood,
    say: say,
    poke: poke,
    playIn: playIn,
    reset: reset,
    get mood() { return el ? el.dataset.mood : null; },
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.LoginCat = API;
})(typeof window !== "undefined" ? window : globalThis);
