/* 摄像头专项面板：动作分类（纯函数）+ 抽屉面板渲染（注入依赖）。
 *
 * 浏览器里挂 window.CameraPanel（app.js 调 CameraPanel.install(...) 注入依赖、
 * CameraPanel.render(d) 取 DOM 节点）；Node 里可直接 require 测试：
 *   - classify(actions) 纯函数，无依赖；
 *   - render(d) 需要 global.document（测试用轻量 DOM 桩）与 install 注入的
 *     { state, api, toast, createEl }。
 *
 * 视频：小米摄像头走专有 P2P 协议，标准取流返回的不是浏览器可播地址，
 *       故"尝试获取"成功也只是尽力；拿不到可播地址就如实说明 + 展示原始返回。
 * 云台/动作：完全按设备 spec 的 action 动态生成；命中方向键模式铺成方向盘，
 *            其余非破坏性动作给通用按钮，破坏性动作（格式化/弹出…）一律不暴露。
 */
(function (root) {
  "use strict";

  var PTZ_SYMBOLS = {
    "pan-left": "←", "pan-right": "→", "tilt-up": "↑", "tilt-down": "↓",
    "zoom-in": "＋", "zoom-out": "－", "rotate": "⟳",
    "rotate-left": "↺", "rotate-right": "↻",
    "go-to-preset": "预设", "ptz": "云台", "ptz-control": "云台",
  };
  // 仅白名单内的"非破坏性"动作才给通用按钮
  var SAFE_ACTION = /^(pan-|tilt-|zoom-|rotate|go-to-preset|ptz|snapshot|calibration|flip|mirror|led|indicator|alarm|siren|notify|mute|volume|talk|push|enable|disable|move)/i;
  // 破坏性 / 危险动作无论是否认得都不暴露按钮，避免误触（格式化存储卡等）
  var DENY_ACTION = /^(format|delete|reset|factory|restore|reboot|power-off|pop-up|eject|clear|remove|add)/i;

  var DIRECTIONS = ["tilt-up", "pan-left", "ptz", "pan-right", "tilt-down"];

  function classify(actions) {
    var ptz = [], others = [], denied = [];
    for (var i = 0; i < (actions || []).length; i++) {
      var a = actions[i];
      if ((a.svc || "").indexOf("p2p-stream") >= 0) continue;  // 取流单独处理
      if (PTZ_SYMBOLS[a.name]) { ptz.push(a); continue; }
      if (DENY_ACTION.test(a.name)) { denied.push(a); continue; }
      if (SAFE_ACTION.test(a.name)) { others.push(a); continue; }
      denied.push(a);  // 其余未白名单动作保守不暴露
    }
    return { ptz: ptz, others: others, denied: denied };
  }

  // ---------------------------------------------------------------- 渲染
  var DEPS = null;

  function install(deps) {
    DEPS = deps || {};
  }

  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function render(d) {
    var state = DEPS.state, createEl = DEPS.createEl || el;
    var wrap = document.createElement("div");
    wrap.className = "ctrl-row cam-panel";
    var title = createEl("label", null, "摄像头");
    wrap.appendChild(title);

    // ---- 实时画面区 ----
    var videoHost = el("div", "cam-video");
    var video = document.createElement("video");
    video.autoplay = true; video.muted = true; video.playsInline = true;
    video.className = "cam-video-el hidden";
    var placeholder = el("div", "cam-placeholder", "实时画面需从设备取流");
    videoHost.appendChild(video);
    videoHost.appendChild(placeholder);
    wrap.appendChild(videoHost);

    var btnRow = el("div", "cam-btns");
    var getBtn = createEl("button", "toggle-btn", "尝试获取实时画面");
    var stopBtn = createEl("button", "toggle-btn", "停止取流");
    btnRow.appendChild(getBtn);
    btnRow.appendChild(stopBtn);
    wrap.appendChild(btnRow);

    var note = el("div", "cam-note dim-note");
    wrap.appendChild(note);

    var prev = state && state.cameraStream && state.cameraStream[String(d.did)];
    if (prev) applyStream(video, placeholder, note, prev);

    getBtn.onclick = function () {
      getBtn.disabled = true;
      note.textContent = "正在向设备请求取流…";
      DEPS.api("/api/camera/stream", { did: String(d.did) }).then(function (r) {
        if (!r.ok) { note.textContent = "取流失败：" + (r.hint || r.error || ""); }
        else {
          if (state) { (state.cameraStream || (state.cameraStream = {}))[String(d.did)] = r; }
          applyStream(video, placeholder, note, r);
        }
      }).catch(function () { note.textContent = "网络异常，取流未成功"; })
        .then(function () { getBtn.disabled = false; });
    };
    stopBtn.onclick = function () {
      DEPS.api("/api/camera/stop", { did: String(d.did) }).then(function () {
        if (state && state.cameraStream) delete state.cameraStream[String(d.did)];
        video.src = ""; video.classList.add("hidden");
        placeholder.classList.remove("hidden");
        placeholder.textContent = "实时画面需从设备取流";
        note.textContent = "已发送停止取流。";
      }).catch(function () { DEPS.toast && DEPS.toast("停止取流失败"); });
    };

    // ---- 云台 / 动作区（按 spec 动态）----
    var cls = classify(d.actions || []);
    if (cls.ptz.length || cls.others.length) {
      var pad = el("div", "cam-pad");
      if (cls.ptz.length) {
        pad.appendChild(el("div", "cam-pad-title", "云台"));
        var grid = el("div", "cam-pad-grid");
        for (var i = 0; i < DIRECTIONS.length; i++) {
          var name = DIRECTIONS[i];
          var a = null;
          for (var j = 0; j < cls.ptz.length; j++) {
            if (cls.ptz[j].name === name) { a = cls.ptz[j]; break; }
          }
          var cell = createEl("button", "cam-pad-btn", a ? PTZ_SYMBOLS[name] : "");
          if (a) { (function (act) { cell.onclick = function () { cameraAction(d, act); }; })(a); }
          else { cell.classList.add("empty"); cell.disabled = true; }
          grid.appendChild(cell);
        }
        pad.appendChild(grid);
      }
      for (var k = 0; k < cls.others.length; k++) {
        (function (act) {
          var b = createEl("button", "toggle-btn cam-act", act.name);
          b.onclick = function () { cameraAction(d, act); };
          pad.appendChild(b);
        })(cls.others[k]);
      }
      wrap.appendChild(pad);
    } else {
      wrap.appendChild(el("div", "cam-note dim-note",
        "此摄像头型号未在 MIoT 标准协议中暴露云台/可控动作"
        + "（旧款创米摄像头通过私有协议控制，PC 端无法直接驱动）。"));
    }
    return wrap;
  }

  function applyStream(video, placeholder, note, r) {
    if (r.playable && r.url) {
      placeholder.classList.add("hidden");
      video.src = r.url; video.classList.remove("hidden");
      if (video.play) { try { video.play(); } catch (e) { /* 部分地址浏览器不支持 */ } }
      note.textContent = "已拿到可播放地址（部分地址浏览器可能不支持）。";
    } else {
      video.classList.add("hidden"); placeholder.classList.remove("hidden");
      placeholder.textContent = "该设备无法在 PC 浏览器直接出画面";
      note.textContent = r.note || "未能取到可播放画面。";
      if (r.raw !== undefined && r.raw !== null) {
        var raw = el("details", "cam-raw");
        raw.appendChild(el("summary", null, "查看设备返回的原始数据"));
        raw.appendChild(el("pre", null, JSON.stringify(r.raw, null, 2)));
        note.appendChild(raw);
      }
    }
  }

  function cameraAction(d, a) {
    DEPS.api("/api/camera/action", { did: String(d.did), siid: a.siid, aiid: a.aiid })
      .then(function (r) {
        if (!r.ok) { DEPS.toast && DEPS.toast(r.hint || r.error || "动作执行失败"); }
        else { DEPS.toast && DEPS.toast("已发送：" + a.name); }
      }).catch(function () { DEPS.toast && DEPS.toast("网络异常"); });
  }

  var API = {
    PTZ_SYMBOLS: PTZ_SYMBOLS,
    SAFE_ACTION: SAFE_ACTION,
    DENY_ACTION: DENY_ACTION,
    DIRECTIONS: DIRECTIONS,
    classify: classify,
    install: install,
    render: render,
    applyStream: applyStream,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.CameraPanel = API;
})(typeof window !== "undefined" ? window : globalThis);
