/* 米家Web版前端。无构建步骤，原生 JS。
 * 版本竞态：用户操作递增 state.ver[did]，轮询回来的结果若落后于版本则丢弃。 */
"use strict";

const state = {
  devices: {},          // did -> view
  live: {},             // did -> {on, brightness, ...}
  ver: {},              // did -> int（用户操作版本号）
  tree: { homes: [], unassigned: [] },  // 家庭 → 房间两级（云端）
  groups: [],                          // 自定义分组（本机持久化）
  filter: "all",                       // 当前筛选节点 key
  kw: "",
  logged: false,
  drawerDid: null,
  syncing: false,       // 登录后设备列表云端同步中（限流退避）
  syncTimer: null,
  history: {},          // did -> {key: [[ts, value], ...]} 趋势曲线数据
  drawerHours: 24,      // 抽屉曲线时间窗口
  holdDid: null,        // 正在拖滑杆的设备：轮询期间不重建它的卡片/抽屉
  weather: null,        // ④ 天气卡片数据（不再是顶部通栏）
  weatherSize: localStorage.getItem("mi-weather-size") || "md",
  weatherCity: localStorage.getItem("mi-weather-city") || "",
  weatherDrawer: false, // 当前抽屉展示的是天气详情而非设备
  automations: [],      // ⑤ 自动化清单
  autoCount: 0,
  autoEnabled: 0,
  autoWritable: false,  // Edit 已验证后可改名 / 启停
  autoCreateSupported: false,
  autoDeleteSupported: false,
  autoCreateOpen: false,   // 新建表单是否展开（不持久化，刷新默认收起）
  autoTemplateSig: "",     // 模板下拉的选项签名，避免刷新时重置用户选择
  autoDrawer: false,
  autoSceneId: null,
  layout: { sizes: {}, order: [] },  // ⑦ 卡片尺寸覆盖 + 拖拽顺序（本机持久化）
  draggingDid: null,                 // 正在拖拽的设备 did
  mainTab: localStorage.getItem("mi-main-tab") || "devices",  // ⑧ 主区标签页
  cameraStream: {},                  // did -> 最近一次取流结果（轮询重建抽屉时保留）
  homesCount: 0,                     // 本次渲染涉及几个家庭（>1 时副标题带家庭名）
};

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

function createEl(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = text;
  return e;
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.remove("hidden");
  clearTimeout(t._h);
  t._h = setTimeout(() => t.classList.add("hidden"), 2600);
}

async function api(path, body) {
  const opt = body
    ? { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body) }
    : {};
  const r = await fetch(path, opt);
  return r.json();
}

function bump(did) {
  state.ver[did] = (state.ver[did] || 0) + 1;
}

/* ---------------- 自定义名称 / 卡片外显值（localStorage） ---------------- */
function namesMap() {
  try { return JSON.parse(localStorage.getItem("mi-names") || "{}"); }
  catch (e) { return {}; }
}
function displayName(d) {
  return namesMap()[d.did] || d.name;
}
function setName(did, name) {
  const m = namesMap();
  if (name) m[did] = name; else delete m[did];
  localStorage.setItem("mi-names", JSON.stringify(m));
}
function metricsMap() {
  try { return JSON.parse(localStorage.getItem("mi-metrics") || "{}"); }
  catch (e) { return {}; }
}
function metricsOf(did) {
  return metricsMap()[did] || [];
}
function setMetrics(did, keys) {
  const m = metricsMap();
  if (keys && keys.length) m[did] = keys.slice(0, 2);
  else delete m[did];
  localStorage.setItem("mi-metrics", JSON.stringify(m));
}
function metricLabel(key, d) {
  return CardTypes.labelOf(key, d);
}

/* ---------------- 主题系统：7 套预设 × 浅/深 × 自定义主色 ---------------- */
const THEME = {
  mode: localStorage.getItem("mi-mode") || "light",
  preset: localStorage.getItem("mi-preset") || "blue",
  accent: localStorage.getItem("mi-accent") || "",
};

function hexToRgb(hex) {
  const m = hex.replace("#", "");
  return [parseInt(m.slice(0, 2), 16), parseInt(m.slice(2, 4), 16),
          parseInt(m.slice(4, 6), 16)];
}
function rgbToHex(r, g, b) {
  const c = (v) => Math.max(0, Math.min(255, Math.round(v))).toString(16);
  return "#" + c(r).padStart(2, "0") + c(g).padStart(2, "0") + c(b).padStart(2, "0");
}
function mix(hex1, hex2, ratio) {
  const a = hexToRgb(hex1), b = hexToRgb(hex2);
  return rgbToHex(a[0] + (b[0] - a[0]) * ratio,
                  a[1] + (b[1] - a[1]) * ratio,
                  a[2] + (b[2] - a[2]) * ratio);
}
function hexToRgba(hex, alpha) {
  const [r, g, b] = hexToRgb(hex);
  return `rgba(${r},${g},${b},${alpha})`;
}

function applyTheme() {
  const root = document.documentElement;
  root.dataset.theme = THEME.mode;
  root.dataset.preset = THEME.preset;
  // 自定义主色：现场推导 hover/柔和色
  if (THEME.preset === "custom" && /^#[0-9a-fA-F]{6}$/.test(THEME.accent)) {
    const dark = THEME.mode === "dark";
    const base = THEME.accent;
    const strong = dark ? mix(base, "#ffffff", .22) : mix(base, "#000000", .18);
    root.style.setProperty("--accent", base);
    root.style.setProperty("--accent-strong", strong);
    root.style.setProperty("--accent-soft", hexToRgba(base, dark ? .13 : .10));
    root.style.setProperty("--accent-soft-2", hexToRgba(base, dark ? .26 : .22));
  } else {
    root.style.removeProperty("--accent");
    root.style.removeProperty("--accent-strong");
    root.style.removeProperty("--accent-soft");
    root.style.removeProperty("--accent-soft-2");
  }
  localStorage.setItem("mi-mode", THEME.mode);
  localStorage.setItem("mi-preset", THEME.preset);
  localStorage.setItem("mi-accent", THEME.accent);
  // 兼容旧键（旧版本只存 mi-theme）
  localStorage.setItem("mi-theme", THEME.mode);
  renderThemePop();
}

function renderThemePop() {
  $$(".tp-mode").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === THEME.mode));
  $$(".sw[data-preset]").forEach((b) =>
    b.classList.toggle("active", b.dataset.preset === THEME.preset));
  const custom = $(".sw.custom");
  if (custom) custom.classList.toggle("active", THEME.preset === "custom");
  const picker = $("#accent-picker");
  if (picker && /^#[0-9a-fA-F]{6}$/.test(THEME.accent)) picker.value = THEME.accent;
}

function bindThemePop() {
  $("#btn-theme").onclick = () => $("#theme-pop").classList.toggle("hidden");
  $$(".tp-mode").forEach((b) => {
    b.onclick = () => { THEME.mode = b.dataset.mode; applyTheme(); };
  });
  $$(".sw[data-preset]").forEach((b) => {
    b.onclick = () => { THEME.preset = b.dataset.preset; applyTheme(); };
  });
  $("#accent-picker").oninput = (e) => {
    THEME.accent = e.target.value;
    THEME.preset = "custom";
    applyTheme();
  };
  $("#tp-reset").onclick = () => {
    THEME.mode = "light"; THEME.preset = "blue"; THEME.accent = "";
    applyTheme();
    toast("已恢复默认主题");
  };
  document.addEventListener("click", (e) => {
    const pop = $("#theme-pop");
    if (pop.classList.contains("hidden")) return;
    if (!pop.contains(e.target) && e.target !== $("#btn-theme"))
      pop.classList.add("hidden");
  });
}

/* ---------------- ④ 天气卡片 ----------------
 * 顶部固定横幅已移除，天气作为一张卡片进入设备网格，与设备共用三尺寸排版。
 * 只在「全部设备」且无搜索词时出现：房间/自定义分组视图是设备清单，不插天气。
 */
async function loadWeather() {
  // 网络不通时也要留一张卡，而不是让整块天气消失（抽屉里可手动刷新）
  const fallback = {
    city: state.weatherCity || "", unavailable: true,
    text: "天气暂不可用", code: 3,
  };
  try {
    const q = state.weatherCity ? "?city=" + encodeURIComponent(state.weatherCity) : "";
    const r = await api("/api/weather" + q);
    state.weather = (r && r.weather) || state.weather || fallback;
  } catch (e) {
    state.weather = state.weather || fallback;  // 失败不打扰，保留上一次数据
  }
  renderGrid();
  if (state.weatherDrawer) syncWeatherDrawer();
}

function setWeatherSize(size) {
  if (!WeatherCard.SIZES.includes(size)) return;
  state.weatherSize = size;
  localStorage.setItem("mi-weather-size", size);
  renderGrid();
  if (state.weatherDrawer) syncWeatherDrawer();
}

async function setWeatherCity(city) {
  state.weatherCity = city || "";
  if (city) localStorage.setItem("mi-weather-city", city);
  else localStorage.removeItem("mi-weather-city");
  toast(city ? "天气城市已切换为 " + city : "已恢复默认城市");
  await loadWeather();
}

function openWeatherDrawer() {
  state.drawerDid = null;   // 避免 3 秒轮询把天气抽屉当成设备抽屉重建
  state.autoDrawer = false;
  state.autoSceneId = null;
  state.weatherDrawer = true;
  $("#dr-name").textContent = "天气";
  $("#drawer").classList.remove("hidden");
  $("#drawer-mask").classList.remove("hidden");
  syncWeatherDrawer();
}

function syncWeatherDrawer() {
  const body = $("#dr-body");
  body.innerHTML = "";
  body.appendChild(WeatherCard.drawer(state.weather || {}, state.weatherSize, {
    sparkline: CardTypes.sparkline,
    onSize: setWeatherSize,
    onCity: setWeatherCity,
    onRetry: loadWeather,
  }));
}

/* ---------------- 设备与分组 ---------------- */
async function loadGroups() {
  try {
    const r = await api("/api/groups");
    state.groups = r.groups || [];
  } catch (e) {
    state.groups = [];
  }
}

async function postGroups(payload) {
  const r = await api("/api/groups", payload);
  if (!r.ok) { toast(r.error || "分组操作失败"); return false; }
  state.groups = r.groups || [];
  return true;
}

async function loadDevices() {
  const r = await api("/api/devices");
  state.logged = !!r.logged_in;
  if (!state.logged) {
    showLoginPage();
    return;
  }
  hideLoginPage();
  $("#login-state").textContent = "已登录";
  state.devices = {};
  for (const d of r.devices || []) state.devices[d.did] = d;
  await loadGroups();
  state.tree = Groups.buildTree(Object.values(state.devices));
  // 分组被删 / 云端家庭改名后，当前筛选节点可能已不存在
  if (!Groups.nodes(state.tree, state.groups).some((n) => n.key === state.filter)) {
    state.filter = "all";
  }
  renderRooms();
  renderGrid();
}

async function loadLayout() {
  try {
    const r = await api("/api/layout");
    if (r.ok) state.layout = { sizes: r.sizes || {}, order: r.order || [] };
  } catch (e) { /* 离线/失败不影响其它功能 */ }
}

/** ⑦ 应用尺寸覆盖：详情里手动设定的尺寸优先，否则按类型自动。 */
function cardSize(d) {
  return state.layout.sizes[d.did] || Cards.sizeOf(d);
}

/** 卡片上除了「图标 + 名称 + 状态」还有没有别的内容。
 *  与 card_types.js 的 is-bare 收口同一判据：离线不渲染任何控件，
 *  声明了能力但实时值没拿到的设备也就没有读数——这两类都不该占大卡。 */
function cardHasContent(d) {
  const live = state.live[d.did] || {};
  if (CardTypes.readoutEntries(d, live).length) return true;
  if (!d.online) return false;
  const ctrls = (d.controls || []).filter((c) => c.writable);
  return ctrls.length > 0 || (d.switches || []).length > 1;
}

/** ⑦ 按拖拽顺序稳定排序（未拖拽过的设备保持默认相对顺序排末尾）。 */
function applyOrder(list) {
  const order = state.layout.order || [];
  const pos = new Map(order.map((did, i) => [did, i]));
  return list.slice().sort((a, b) => {
    const ia = pos.has(String(a.did)) ? pos.get(String(a.did)) : 1e9;
    const ib = pos.has(String(b.did)) ? pos.get(String(b.did)) : 1e9;
    if (ia !== ib) return ia - ib;
    return 0;  // 同序或都未排序：保持原插入顺序
  });
}

async function saveOrder() {
  const order = (applyOrder(Object.values(state.devices)).map((d) => String(d.did)));
  try {
    await api("/api/layout/order", { order });
  } catch (e) { /* 持久化失败静默 */ }
}

/** 拖放时定位光标下的设备卡（穿透正在拖拽的卡本身）。 */
function cardUnder(x, y) {
  const el = document.elementFromPoint(x, y);
  const card = el && el.closest && el.closest(".device-card");
  if (!card || card.dataset.did === state.draggingDid) return null;
  return card;
}

/* ---------------- 全屏登录页 ---------------- */
let qrTimer = null;
let qrTabActive = true;

function showLoginPage() {
  document.body.classList.add("logged-out");
  $("#login-page").classList.remove("hidden");
  $("#login-state").textContent = "未登录";
  if (qrTabActive) startQr();
}

function hideLoginPage() {
  document.body.classList.remove("logged-out");
  $("#login-page").classList.add("hidden");
  stopQrPoll();
}

function stopQrPoll() {
  if (qrTimer) { clearInterval(qrTimer); qrTimer = null; }
}

function onLoginSuccess() {
  toast("登录成功");
  // 猫先跳一下再收页：把「等登录」的最后半秒留给它，数据照常并行加载
  let gone = false;
  const go = () => {
    if (gone) return;
    gone = true;
    hideLoginPage();
  };
  if (typeof LoginCat !== "undefined") LoginCat.playIn(700, go);
  else go();
  stopQrPoll();
  loadDevices().then(() => {
    pollFull(); loadScenes(); loadAutomations(); loadEvents();
  });
  startSyncWatch();
}

/* 登录后设备列表可能被小米限流（-127），后台在退避补拉；
 * 这里每 5 秒重取一次，拿到设备或超时（2 分钟）为止 */
function startSyncWatch() {
  if (state.syncTimer) { clearInterval(state.syncTimer); }
  state.syncing = true;
  renderGrid();
  const t0 = Date.now();
  state.syncTimer = setInterval(async () => {
    if (!state.logged || Date.now() - t0 > 120000) {
      state.syncing = false;
      clearInterval(state.syncTimer);
      state.syncTimer = null;
      renderGrid();
      return;
    }
    if (Object.keys(state.devices).length) {
      state.syncing = false;
      clearInterval(state.syncTimer);
      state.syncTimer = null;
      return;
    }
    await loadDevices();
    renderGrid();
  }, 5000);
}

async function startQr() {
  stopQrPoll();
  setQrStatus("正在获取二维码…", "");
  $("#qr-overlay").classList.add("hidden");
  try {
    const r = await api("/api/login/qr/start", {});
    if (!r.ok) {
      if (r.error && r.error.indexOf("已登录") >= 0) { onLoginSuccess(); return; }
      setQrStatus(r.error || "二维码获取失败", "err");
      showQrOverlay("获取失败");
      return;
    }
    $("#qr-img").src = "/api/login/qr/image?t=" + Date.now();
    setQrStatus("请使用米家 App 扫码", "");
    qrTimer = setInterval(pollQr, 2500);
  } catch (e) {
    setQrStatus("网络异常，稍后重试", "err");
  }
}

async function pollQr() {
  try {
    const r = await api("/api/login/qr/poll");
    if (r.status === "ok" || r.logged_in) {
      setQrStatus("登录成功，正在进入…", "ok");
      onLoginSuccess();
    } else if (r.restoring) {
      // 本机 token 恢复中（通常在等小米风控解除），页面自动等待
      setQrStatus("正在恢复登录（等待小米风控解除）…", "");
    } else if (r.status === "expired") {
      stopQrPoll();
      setQrStatus("二维码已过期", "err");
      showQrOverlay("二维码已过期");
    } else if (r.status === "error") {
      stopQrPoll();
      setQrStatus(r.error || "扫码登录出错", "err");
      showQrOverlay("出错了");
    } else if (r.status === "waiting") {
      setQrStatus("请使用米家 App 扫码", "");
    }
  } catch (e) { /* 短暂网络抖动继续等 */ }
}

function setQrStatus(text, cls) {
  const el = $("#qr-status");
  el.textContent = text;
  el.className = "qr-status" + (cls ? " " + cls : "");
  // 二维码状态就是猫的心情：取码→安静待着，等扫码→坐起来，成功→跳，过期→垂耳朵
  if (typeof LoginCat !== "undefined") LoginCat.setMood(LoginCat.moodOf(text, cls));
}

function showQrOverlay(text) {
  $("#qr-overlay-text").textContent = text;
  $("#qr-overlay").classList.remove("hidden");
}

/* 登录页签切换 */
$$(".lp-tab").forEach((b) => {
  b.onclick = () => {
    $$(".lp-tab").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    qrTabActive = b.dataset.tab === "qr";
    $("#lp-qr").classList.toggle("hidden", !qrTabActive);
    $("#lp-pwd").classList.toggle("hidden", qrTabActive);
    if (qrTabActive) startQr();
    else stopQrPoll();
  };
});
$("#qr-refresh").onclick = startQr;
$("#lp-mode").onclick = () => {
  THEME.mode = THEME.mode === "dark" ? "light" : "dark";
  applyTheme();
};

function renderRooms() {
  const nav = $("#room-list");
  nav.innerHTML = "";
  const list = Groups.nodes(state.tree, state.groups);
  let customStarted = false;
  for (const n of list) {
    if (n.type === "group" && !customStarted) {
      customStarted = true;
      const sec = document.createElement("div");
      sec.className = "nav-section";
      const t = document.createElement("span");
      t.textContent = "自定义分组";
      const add = document.createElement("button");
      add.className = "nav-add";
      add.textContent = "+";
      add.title = "新建分组";
      add.onclick = async () => {
        const name = (prompt("新分组名称") || "").trim();
        if (!name) return;
        if (await postGroups({ action: "create", name })) {
          renderRooms(); renderGrid();
          if (state.drawerDid) syncDrawer(state.drawerDid);
        }
      };
      sec.appendChild(t); sec.appendChild(add);
      nav.appendChild(sec);
    }
    const el = document.createElement("div");
    el.className = "room-item nav-" + n.type +
      (state.filter === n.key ? " active" : "");
    const label = document.createElement("span");
    label.className = "nav-label";
    label.textContent = n.label;
    const num = document.createElement("span");
    num.className = "nav-count";
    num.textContent = n.count;
    el.appendChild(label); el.appendChild(num);
    if (n.type === "group") {
      const del = document.createElement("button");
      del.className = "nav-del";
      del.textContent = "×";
      del.title = "删除分组";
      del.onclick = async (e) => {
        e.stopPropagation();
        if (!confirm("删除分组「" + n.label + "」？设备不会被删除。")) return;
        if (await postGroups({ action: "delete", id: n.id })) {
          if (state.filter === n.key) state.filter = "all";
          renderRooms(); renderGrid();
          if (state.drawerDid) syncDrawer(state.drawerDid);
        }
      };
      el.appendChild(del);
    }
    el.onclick = () => { state.filter = n.key; renderRooms(); renderGrid(); };
    nav.appendChild(el);
  }
}

function visibleDevices() {
  const list = Object.values(state.devices).filter((d) => {
    if (!Groups.matches(state.filter, d, state.groups)) return false;
    if (state.kw) {
      const hay = (displayName(d) + " " + d.name + " " +
        (d.model || "") + " " + (d.product || "") + " " +
        (d.home || "") + " " + (d.room || "")
      ).toLowerCase();
      if (!hay.includes(state.kw)) return false;
    }
    return true;
  });
  return applyOrder(list);
}

/* ---------------- ⑧ 主区标签页：设备 / 场景 / 自动化 / 日志 ---------------- */
function applyMainTab() {
  const t = state.mainTab || "devices";
  const map = {
    devices: ["stat-strip", "device-grid"],
    scenes: ["scene-panel"],
    automations: ["automation-panel"],
    logs: ["event-panel"],
  };
  const show = new Set(map[t] || []);
  for (const id of ["stat-strip", "device-grid", "scene-panel",
                     "automation-panel", "event-panel"]) {
    const el = document.getElementById(id);
    if (el) el.classList.toggle("hidden", !show.has(id));
  }
  $$("#main-tabs .tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === t));
}

function renderGrid() {
  const grid = $("#device-grid");
  if (!grid._dragBound) {
    grid._dragBound = true;
    grid.addEventListener("dragover", (e) => {
      e.preventDefault();
      if (!state.draggingDid) return;
      const tgt = cardUnder(e.clientX, e.clientY);
      document.querySelectorAll(".device-card.drop-before")
        .forEach((x) => x.classList.remove("drop-before"));
      if (tgt && tgt.dataset.did !== state.draggingDid) tgt.classList.add("drop-before");
    });
    grid.addEventListener("drop", (e) => {
      e.preventDefault();
      const drag = state.draggingDid;
      if (!drag) return;
      const tgt = cardUnder(e.clientX, e.clientY);
      const order = applyOrder(Object.values(state.devices)).map((d) => String(d.did));
      const from = order.indexOf(drag);
      if (from < 0) return;
      order.splice(from, 1);
      let idx = order.length;
      if (tgt && tgt.dataset.did && tgt.dataset.did !== drag) {
        const j = order.indexOf(String(tgt.dataset.did));
        if (j >= 0) idx = j;
      }
      order.splice(idx, 0, drag);
      state.layout.order = order;
      saveOrder();
      renderGrid();
    });
  }
  // 正在拖滑杆的设备保留原 DOM，否则 3 秒轮询重建会打断拖拽
  const held = state.holdDid
    ? Array.from(grid.children).find((x) => x.dataset && x.dataset.did === state.holdDid)
    : null;
  grid.innerHTML = "";
  const list = visibleDevices();
  if (!list.length && state.logged) {
    // 登录后设备列表可能还在云端限流退避中（后台补拉），给同步提示
    const tip = document.createElement("div");
    tip.className = "grid-tip";
    tip.textContent = state.syncing
      ? "正在从云端同步设备列表…"
      : (state.filter !== "all" ? "该分组暂无设备" : "暂无设备");
    grid.appendChild(tip);
  }
  // 天气卡放在网格首位；筛选到具体房间/分组或搜索时不显示
  if (state.logged && state.filter === "all" && !state.kw && state.weather) {
    grid.appendChild(WeatherCard.render(state.weather, state.weatherSize, {
      sparkline: CardTypes.sparkline,
      onSize: setWeatherSize,
      onOpen: openWeatherDrawer,
    }));
  }
  // 副标题要带家庭名的判定依据（多家庭并存时「客厅」会重名）
  state.homesCount = new Set(list.map((d) => d.home).filter(Boolean)).size;
  for (const d of list) {
    if (held && String(d.did) === state.holdDid) grid.appendChild(held);
    else grid.appendChild(card(d));
  }
  renderStatStrip(list);
}

/* ---------------- 统计条 ----------------
 * 只读「当前范围」（家庭/房间/搜索筛过的 list），并按常用类型分组：
 * 照明含开关与灯具，环境含温湿度/空调/净化，传感器只放纯探测器，其余归其它。
 * 空组不占位，窄房间里不会出现一排 0。
 */
const STAT_GROUPS = [["light", "照明"], ["env", "环境"],
                     ["sensor", "传感器"], ["other", "其它"]];

function statGroupOf(d) {
  const c = Cards.categoryOf(d);
  if (c === "light" || c === "switch") return "light";
  if (c === "climate-sensor" || c === "climate" || c === "purifier") return "env";
  if (c === "sensor") return "sensor";
  return "other";
}

function renderStatStrip(list) {
  const strip = $("#stat-strip");
  if (!strip) return;
  const online = list.filter((d) => d.online).length;
  // "开着"统计：多键开关任一路开着即算（单键看 on）
  const onCount = list.filter((d) => {
    const l = state.live[d.did] || {};
    const sws = d.switches || [];
    return sws.length > 1 ? sws.some((s) => l[s.key] === true) : l.on === true;
  }).length;
  const acc = {};
  for (const d of list) {
    const k = statGroupOf(d);
    acc[k] = (acc[k] || 0) + 1;
  }
  strip.innerHTML = "";
  const cell = (label, value) => {
    const s = document.createElement("span");
    s.textContent = label + " ";
    const b = document.createElement("b");
    b.textContent = value;
    s.appendChild(b);
    strip.appendChild(s);
  };
  cell("设备", list.length);
  cell("在线", online);
  cell("开着", onCount);
  for (const [k, label] of STAT_GROUPS) {
    if (acc[k]) cell(label, acc[k]);
  }
}

/* ---------------- 卡片工厂 ----------------
 * ③ 阶段按类别注册专用渲染器（灯 / 温湿度 / 空调…），未注册走通用卡片。
 * card() 只负责分派 + 打尺寸/类别标记，网格排版交给 CSS 的 .sz-*。
 */
const CARD_RENDERERS = {};
function setHold(did, on) {
  if (on) state.holdDid = String(did);
  else if (state.holdDid === String(did)) state.holdDid = null;
}
CardTypes.install(CARD_RENDERERS, {
  baseCard, state, $, toggle, setControl, displayName, relTime, openDrawer,
  Cards, hold: setHold,
  metricsOf,   // 用户自选的「卡片外显值」→ 读数区优先排序
});
if (typeof CameraPanel !== "undefined") {
  CameraPanel.install({ state, api, toast, createEl });
}

function card(d) {
  const cat = Cards.categoryOf(d);
  const size = cardSize(d);
  const render = CARD_RENDERERS[cat];
  const el = render ? render(d, size) : baseCard(d, size);
  el.classList.add("sz-" + size, "cat-" + cat);
  el.dataset.category = cat;
  el.dataset.size = size;
  el.draggable = true;
  el.addEventListener("dragstart", (e) => {
    state.draggingDid = String(d.did);
    el.classList.add("dragging");
    if (e.dataTransfer) { e.dataTransfer.effectAllowed = "move"; }
  });
  el.addEventListener("dragend", () => {
    state.draggingDid = null;
    el.classList.remove("dragging");
    document.querySelectorAll(".device-card.drop-before")
      .forEach((x) => x.classList.remove("drop-before"));
  });
  return el;
}

/* 卡片状态文案：只说有意义的话。
 *
 * 以前这里是「运行中 · 在线 · 最近在线 7 分钟前 · 温度 24°C」堆成一行，
 * 既有自相矛盾的「运行中 · 离线」，又把读数挤成了小尾巴。
 * 现在：离线只说「离线」；多键说「3/4 路开」；单键说「已开启/已关闭」；
 * 没有电源能力的设备（传感器/网关/摄像头）不再硬造状态——
 * 没状态就不显示这一行，把纵向空间让给读数。
 */
function cardStatus(d, o) {
  if (o.offline) return "离线";
  if (o.multi) {
    const n = o.sws.filter((s) => o.live[s.key] === true).length;
    return n + "/" + o.sws.length + " 路开";
  }
  if (!Cards.toggleable(d)) return "";
  if (o.isOn) return "已开启";
  return o.live.on === false ? "已关闭" : "状态未知";
}

/* 没有状态可说的设备（网关/摄像头/通用件）用「房间」充当第二行。
 * 多家庭并存时带上家庭名——三个家里都有「客厅」，只写客厅会分不清。 */
function cardContext(d) {
  const room = (d.room || "").trim();
  if (!room) return CardTypes.productLabel(d) || "";
  return (state.homesCount > 1 && d.home) ? d.home + " · " + room : room;
}

function baseCard(d, size) {
  const live = state.live[d.did] || {};
  const sws = d.switches || [];
  const multi = sws.length > 1;
  const isOn = multi
    ? sws.some((s) => live[s.key] === true)
    : live.on === true;
  const offline = !d.online;
  const showSwitch = Cards.toggleable(d);
  const compact = size === "sm";
  const cat = Cards.categoryOf(d);
  const el = document.createElement("div");
  el.className = "device-card " + (isOn ? "on" : "off") + (offline ? " offline" : "");
  el.dataset.did = d.did;
  // 类型色由 CSS 的 [data-category] 决定，这里先落值，插入 DOM 即可上色
  el.dataset.category = cat;

  /* ---- 头部：类型图标 + 名称/状态 + 电源开关 ---- */
  const head = document.createElement("div");
  head.className = "dc-head";

  const icon = document.createElement("div");
  icon.className = "dc-icon";
  icon.title = Cards.CATEGORY_LABELS[cat] || "";
  if (typeof DeviceIcons !== "undefined") icon.innerHTML = DeviceIcons.svg(cat);
  head.appendChild(icon);

  const titles = document.createElement("div");
  titles.className = "dc-titles";
  const name = document.createElement("div");
  name.className = "dc-name";
  name.textContent = displayName(d);
  name.title = displayName(d);   // 两行仍截断时，悬停看全名
  titles.appendChild(name);

  const stateText = cardStatus(d, { multi, sws, isOn, offline, live });
  const subText = stateText || cardContext(d);
  if (subText) {
    const sub = document.createElement("div");
    // 有状态才画状态点；纯房间名是上下文，不该冒充「在线/离线」
    sub.className = "dc-sub" + (offline ? " is-offline" : "")
      + (stateText ? "" : " is-context");
    if (stateText) {
      sub.appendChild(document.createElement("span")).className = "dot";
    }
    sub.appendChild(document.createTextNode(subText));
    titles.appendChild(sub);
  }
  head.appendChild(titles);

  // 单键开关放进头部右侧（不再绝对定位）：避免与两行名称重叠，
  // 也让「图标—名称—开关」在同一条视觉基线上。
  if (showSwitch && !multi && !offline) {
    const sw = document.createElement("button");
    sw.className = "mini-switch in-head" + (isOn ? " on" : "");
    sw.title = "开关";
    sw.onclick = (e) => {
      e.stopPropagation();
      toggle(d.did, !isOn, sws.length ? sws[0].key : "on");
    };
    head.appendChild(sw);
  }
  el.appendChild(head);

  /* ---- 多键开关：逐路独立，不做整机主开关（防"直控只控第一路"） ----
   * 两列铺开：三键开关本来要占三行，行高固定后会把卡撑破。
   * 超过 4 路只铺前 4 路，剩下的提示去抽屉——卡片是速览，不是控制台。 */
  if (showSwitch && multi && !offline) {
    const wrap = document.createElement("div");
    wrap.className = "dc-switches";
    sws.slice(0, 4).forEach((s, i) => {
      const row = document.createElement("div");
      row.className = "sw-row";
      const lb = document.createElement("span");
      lb.className = "sw-label";
      lb.textContent = CardTypes.switchLabel(s, i);
      lb.title = lb.textContent;
      const b = document.createElement("button");
      b.className = "mini-switch" + (live[s.key] === true ? " on" : "");
      b.title = s.label || s.key;
      b.onclick = (e) => {
        e.stopPropagation();
        toggle(d.did, live[s.key] !== true, s.key);
      };
      row.appendChild(lb);
      row.appendChild(b);
      wrap.appendChild(row);
    });
    el.appendChild(wrap);
    if (sws.length > 4) {
      const more = document.createElement("div");
      more.className = "sw-more";
      more.textContent = "另有 " + (sws.length - 4) + " 路，点开设备控制";
      el.appendChild(more);
    }
  }

  /* ---- 快捷操作：枚举控件（档位/模式）铺成按钮；摆风做胶囊 ----
   * 离线时整块不渲染：点了也不会成功的按钮，只会让人以为程序坏了。
   * 小卡不铺（高度不够，且点开抽屉就能调）。
   * 预算：同一 key 只铺一次（多键开关每个通道都带一个同名 mode，
   * 全铺出来会出现重复按钮），整卡最多 6 个 chip；中卡如果还要放滑杆，
   * 就整块不铺——固定行高下「滑杆 + 胶囊」放不进去，硬塞会被裁掉。
   * 多键开关已经占了两行，也不再叠胶囊。 */
  const hasSliders = CardTypes.cardControls(d, cat, size).length > 0;
  const roomForChips = !compact && !offline
    && !(multi && showSwitch)
    && !(hasSliders && size === "md");
  if (roomForChips) {
    const acts = document.createElement("div");
    acts.className = "dc-actions";
    const seenChip = new Set();
    let chipCount = 0;
    for (const c of (d.controls || [])) {
      if (chipCount >= 6) break;
      if (!c.writable || seenChip.has(c.key)) continue;
      if (c.kind === "enum" && (c.key === "fan-level" || c.key === "mode")
          && c.options && c.options.length <= 6) {
        seenChip.add(c.key);
        for (const o of c.options) {
          if (chipCount >= 6) break;
          const b = document.createElement("button");
          b.className = "chip" + (live[c.key] === o.v ? " active" : "");
          b.textContent = o.t;
          b.onclick = (e) => { e.stopPropagation(); setControl(d.did, c, o.v); };
          acts.appendChild(b);
          chipCount++;
        }
      } else if ((c.key === "horizontal-swing" || c.key === "vertical-swing")
                 && c.kind === "bool") {
        seenChip.add(c.key);
        const b = document.createElement("button");
        b.className = "chip swing" + (live[c.key] ? " active" : "");
        b.textContent = (c.key === "horizontal-swing" ? "↔ 摇头" : "↕ 摆风");
        b.onclick = (e) => {
          e.stopPropagation();
          setControl(d.did, c, !live[c.key]);
        };
        acts.appendChild(b);
        chipCount++;
      }
    }
    if (acts.children.length) el.appendChild(acts);
  }

  // 大卡：设备信息区 + 扩展位（③ 阶段放曲线 / 亮度色温滑杆）
  if (size === "lg") {
    const detail = document.createElement("div");
    detail.className = "dc-detail";
    const rows = [
      ["产品", CardTypes.productLabel(d) || d.product || d.model || "—"],
      ["位置", [d.home, d.room].filter(Boolean).join(" / ") || "未分配"],
      ["型号", d.model || "—"],
      ["状态", (d.online ? "在线" : "离线") +
        (d.last_seen ? " · " + relTime(d.last_seen) : "")],
    ];
    for (const [k, v] of rows) {
      const row = document.createElement("div");
      row.className = "dc-detail-row";
      const kEl = document.createElement("span");
      kEl.className = "dc-detail-k"; kEl.textContent = k;
      const vEl = document.createElement("span");
      vEl.className = "dc-detail-v"; vEl.textContent = v; vEl.title = v;
      row.appendChild(kEl); row.appendChild(vEl);
      detail.appendChild(row);
    }
    el.appendChild(detail);
    const extra = document.createElement("div");
    extra.className = "dc-extra";
    el.appendChild(extra);
  }

  el.onclick = () => openDrawer(d.did);
  return el;
}

function relTime(ts) {
  const s = (Date.now() / 1000) - ts;
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + " 分钟前";
  if (s < 86400) return Math.round(s / 3600) + " 小时前";
  return Math.round(s / 86400) + " 天前";
}

/* ---------------- 控制 ---------------- */
function toggle(did, on, key) {
  key = key || "on";
  const d = state.devices[did];
  if (d && d.online === false) { toast("设备离线，无法控制"); return; }
  bump(did);
  applyOptimistic(did, { [key]: on });
  if (key === "on1" || key === "on") applyOptimistic(did, { on });
  const done = () => {
    renderGrid();
    if (state.drawerDid === did) syncDrawer(did);  // 抽屉里的开关同步刷新
  };
  api("/api/switch", { did, on, key }).then((r) => {
    if (!r.ok) {
      bump(did);
      applyOptimistic(did, { [key]: !on });
      toast(r.hint || r.error || "操作失败");
    }
    done();
  }).catch(() => {
    bump(did);
    applyOptimistic(did, { [key]: !on });
    toast("网络异常，已回滚");
    done();
  });
}

async function setControl(did, c, value) {
  const d = state.devices[did];
  if (d && d.online === false) { toast("设备离线，无法控制"); return; }
  bump(did);
  applyOptimistic(did, { [c.key]: value });
  try {
    const r = await api("/api/set", {
      did, siid: c.siid, piid: c.piid, value });
    if (!r.ok) {
      bump(did);
      toast(r.hint || r.error || "设置失败");
    }
  } catch (e) {
    bump(did);
    toast("网络异常");
  }
  renderGrid();
  if (state.drawerDid === did) openDrawer(did);
}

function applyOptimistic(did, patch) {
  Object.assign(state.live[did] || (state.live[did] = {}), patch);
}

/* ---------------- 实时轮询：3 秒开关 / 45 秒全量 ---------------- */
let quickBusy = false;
async function pollQuick() {
  if (!state.logged || quickBusy) return;
  quickBusy = true;
  try {
    const snap = { ...state.ver };
    const r = await api("/api/live?quick=1");
    if (r.ok) mergeLive(r.live, snap, true);
  } catch (e) { /* 后端短暂不可达，下一轮再说 */ }
  quickBusy = false;
}

let fullBusy = false;
async function pollFull() {
  if (!state.logged || fullBusy) return;
  fullBusy = true;
  try {
    const snap = { ...state.ver };
    const r = await api("/api/live");
    if (r.ok) mergeLive(r.live, snap, false);
    await loadHistory();
  } catch (e) { /* ignore */ }
  fullBusy = false;
}

/* ---------------- 历史曲线数据 ----------------
 * 卡片批量取短窗口（6 小时）；抽屉按设备取所选窗口并合入 state.history，
 * 这样 3 秒轮询重建抽屉时曲线不会闪掉。 */
async function loadHistory() {
  if (!state.logged) return;
  try {
    const r = await api("/api/history?hours=6&points=72");
    if (r.ok) {
      // 合并不覆盖：抽屉可能已拉过 24 小时/7 天的长窗口
      for (const [did, keys] of Object.entries(r.series || {})) {
        state.history[did] = Object.assign({}, state.history[did] || {}, keys);
      }
      renderGrid();
    }
  } catch (e) { /* ignore */ }
}

async function loadDrawerHistory(did) {
  try {
    const r = await api("/api/history?did=" + encodeURIComponent(did) +
      "&hours=" + state.drawerHours + "&points=96");
    if (!r.ok || state.drawerDid !== did) return;
    const one = (r.series || {})[String(did)] || {};
    state.history[did] = Object.assign({}, state.history[did] || {}, one);
    syncDrawer(did);
    renderGrid();
  } catch (e) { /* ignore */ }
}

function mergeLive(live, snap, quick) {
  for (const [did, cur] of Object.entries(live || {})) {
    if ((state.ver[did] || 0) !== (snap[did] || 0)) continue; // 刚被用户操作，丢弃
    const bucket = state.live[did] || (state.live[did] = {});
    if (quick) {
      // 只合并开关位（on/on1/on2…），多键各路都要跟上，防"弹回"
      for (const k in cur) {
        if (k === "on" || /^on\d+$/.test(k)) bucket[k] = cur[k];
      }
    } else {
      Object.assign(bucket, cur);
    }
  }
  renderGrid();
  if (state.drawerDid) syncDrawer(state.drawerDid);
}

/* ---------------- 详情抽屉 ---------------- */
function openDrawer(did) {
  state.weatherDrawer = false;
  state.autoDrawer = false;
  state.autoSceneId = null;
  state.drawerDid = did;
  const d = state.devices[did];
  if (!d) return;
  $("#dr-name").textContent = displayName(d);
  $("#drawer").classList.remove("hidden");
  $("#drawer-mask").classList.remove("hidden");
  syncDrawer(did);
  loadDrawerHistory(did);
}

function syncDrawer(did) {
  // 抽屉滑杆拖动中不重建，避免 3 秒轮询把滑块拉回旧值
  if (state.holdDid === String(did)) return;
  const d = state.devices[did];
  const live = state.live[did] || {};
  const body = $("#dr-body");
  body.innerHTML = "";
  if (!d) return;

  const info = document.createElement("div");
  info.className = "ctrl-row";
  // 产品名兜底：产品名优先，型号降级为括号注释（用户反馈 #35）
  info.innerHTML = "<label>状态</label><div>" +
    (live.on === true ? "运行中" : live.on === false ? "已关闭" : "状态未知") +
    " · " + (d.online ? "在线" : "离线") +
    "</div><div class='dim-line'>" +
    (d.product || d.model || "") +
    (d.product && d.model && d.product !== d.model
      ? "（" + d.model + "）" : "") + "</div>";
  body.appendChild(info);

  // 全部传感器读数（中文名 + 单位），分类卡片里只显示前几项
  const rds = CardTypes.readoutEntries(d, live);
  if (rds.length) {
    const box = document.createElement("div");
    box.className = "dr-readouts";
    for (const m of rds) {
      const cell = document.createElement("div");
      cell.className = "dr-readout" + (m.primary ? " primary" : "");
      const k = document.createElement("span");
      k.className = "dr-readout-k"; k.textContent = m.label;
      const v = document.createElement("span");
      v.className = "dr-readout-v"; v.textContent = m.text;
      cell.appendChild(k); cell.appendChild(v);
      box.appendChild(cell);
    }
    body.appendChild(box);
  }

  // 自定义名称（只存本机，不影响手机端）
  const rn = document.createElement("div");
  rn.className = "ctrl-row";
  rn.innerHTML = "<label>自定义名称</label>";
  const rinp = document.createElement("input");
  rinp.className = "text-input";
  rinp.value = displayName(d);
  rinp.placeholder = d.name;
  const rbtn = document.createElement("button");
  rbtn.className = "toggle-btn";
  rbtn.textContent = "保存";
  rbtn.onclick = () => {
    setName(did, rinp.value.trim() && rinp.value.trim() !== d.name
      ? rinp.value.trim() : "");
    toast("名称已保存（仅本机）");
    renderGrid();
    openDrawer(did);
  };
  const rreset = document.createElement("button");
  rreset.className = "toggle-btn";
  rreset.textContent = "恢复云端名";
  rreset.onclick = () => {
    setName(did, "");
    toast("已恢复云端名称");
    renderGrid();
    openDrawer(did);
  };
  rn.appendChild(rinp); rn.appendChild(rbtn); rn.appendChild(rreset);
  body.appendChild(rn);

  // ⑦ 卡片尺寸：手动覆盖自动尺寸（大/中/小），本机持久化
  const sizeRow = document.createElement("div");
  sizeRow.className = "ctrl-row";
  sizeRow.innerHTML = "<label>卡片尺寸</label>";
  const curSize = cardSize(d);
  for (const s of [["lg", "大"], ["md", "中"], ["sm", "小"]]) {
    const b = document.createElement("button");
    b.className = "toggle-btn" + (curSize === s[0] ? " active" : "");
    b.textContent = s[1];
    b.onclick = async () => {
      state.layout.sizes[String(did)] = s[0];
      try { await api("/api/layout/size", { did: String(did), size: s[0] }); }
      catch (e) { /* 静默 */ }
      renderGrid();
      openDrawer(did);
    };
    sizeRow.appendChild(b);
  }
  body.appendChild(sizeRow);
  // 手动设了大/中，但这台设备没有可上卡的内容（声明了能力、实时值没拿到，
  // 或者根本没有可控属性），卡片会被自动收成单格。这里说明一句，
  // 免得用户以为尺寸设置坏了。
  if (state.layout.sizes[String(did)] && state.layout.sizes[String(did)] !== "sm"
      && !cardHasContent(d)) {
    const note = document.createElement("div");
    note.className = "dim-note";
    note.textContent = "这台设备暂时没有可显示的状态，卡片已自动收为小尺寸；"
      + "点开抽屉仍可查看全部信息";
    body.appendChild(note);
  }

  const sws = d.switches || [];
  const offline = !d.online;
  if (Cards.toggleable(d) && sws.length > 1) {
    for (const s of sws) {
      const row = document.createElement("div");
      row.className = "ctrl-row";
      const lab = document.createElement("label");
      lab.textContent = CardTypes.switchLabel(s, sws.indexOf(s));
      row.appendChild(lab);
      const b = document.createElement("button");
      b.className = "toggle-btn" + (live[s.key] ? " active" : "");
      b.textContent = live[s.key] ? "关闭" : "打开";
      b.onclick = () => toggle(did, !live[s.key], s.key);
      row.appendChild(b);
      body.appendChild(row);
    }
  } else if (Cards.toggleable(d)) {
    const onRow = document.createElement("div");
    onRow.className = "ctrl-row";
    const onBtn = document.createElement("button");
    onBtn.className = "toggle-btn" + (live.on ? " active" : "");
    onBtn.textContent = live.on ? "关闭" : "打开";
    onBtn.disabled = offline;
    onBtn.onclick = () => toggle(did, !live.on, sws.length ? sws[0].key : "on");
    onRow.appendChild(onBtn);
    body.appendChild(onRow);
  }


  for (const c of d.controls || []) {
    if (!c.writable) continue;
    const row = document.createElement("div");
    row.className = "ctrl-row";
    const lab = document.createElement("label");
    lab.textContent = c.label + (c.unit ? "（" + c.unit + "）" : "");
    row.appendChild(lab);

    if (c.kind === "range") {
      const wrap = document.createElement("div");
      const inp = document.createElement("input");
      inp.type = "range";
      inp.min = c.min; inp.max = c.max; inp.step = c.step || 1;
      inp.value = live[c.key] ?? c.min;
      inp.disabled = offline;
      const val = document.createElement("span");
      val.className = "ctrl-val";
      val.textContent = inp.value;
      inp.oninput = () => { val.textContent = inp.value; };
      inp.addEventListener("pointerdown", () => setHold(did, true));
      inp.onchange = () => {
        setHold(did, false);
        setControl(did, c, Number(inp.value));
      };
      wrap.appendChild(inp); wrap.appendChild(val);
      row.appendChild(wrap);
    } else if (c.kind === "bool") {
      const b = document.createElement("button");
      b.className = "toggle-btn" + (live[c.key] ? " active" : "");
      b.textContent = live[c.key] ? "开" : "关";
      b.disabled = offline;
      b.onclick = () => setControl(did, c, !live[c.key]);
      row.appendChild(b);
    } else if (c.kind === "enum") {
      for (const o of c.options || []) {
        const b = document.createElement("button");
        b.className = "toggle-btn" + (live[c.key] === o.v ? " active" : "");
        b.textContent = o.t;
        b.disabled = offline;
        b.onclick = () => setControl(did, c, o.v);
        row.appendChild(b);
      }
    }
    body.appendChild(row);
  }

  // 卡片外显值选择（最多 2 项，用户反馈 #20）
  const metricKeys = [];
  if (d.readable) metricKeys.push(...Object.keys(d.readable));
  for (const c of d.controls || []) {
    if (c.readable && !metricKeys.includes(c.key)) metricKeys.push(c.key);
  }
  if (metricKeys.length) {
    const mp = document.createElement("div");
    mp.className = "ctrl-row";
    mp.innerHTML = "<label>卡片外显值（最多 2 项）</label>";
    const picked = metricsOf(did);
    for (const k of metricKeys) {
      const b = document.createElement("button");
      b.className = "toggle-btn" + (picked.includes(k) ? " active" : "");
      b.textContent = metricLabel(k, d);
      b.onclick = () => {
        let cur = metricsOf(did);
        if (cur.includes(k)) cur = cur.filter((x) => x !== k);
        else cur = [...cur, k].slice(-2);
        setMetrics(did, cur);
        renderGrid();
        syncDrawer(did);
      };
      mp.appendChild(b);
    }
    body.appendChild(mp);
  }

  // 摄像头专项：实时画面 + 云台/动作（按 spec 动态生成）
  if (Cards.categoryOf(d) === "camera" && typeof CameraPanel !== "undefined") {
    body.appendChild(CameraPanel.render(d));
  }

  // 自定义分组：把这台设备加入 / 移出（跨家庭组合）
  const gp = document.createElement("div");
  gp.className = "ctrl-row";
  gp.innerHTML = "<label>自定义分组</label>";
  if (!state.groups.length) {
    const hint = document.createElement("span");
    hint.className = "dim-note";
    hint.textContent = "在左侧「自定义分组」点 + 新建";
    gp.appendChild(hint);
  }
  for (const g of state.groups) {
    const inside = (g.dids || []).map(String).includes(String(did));
    const b = document.createElement("button");
    b.className = "toggle-btn" + (inside ? " active" : "");
    b.textContent = g.name;
    b.onclick = async () => {
      const ok = await postGroups({
        action: inside ? "remove" : "add", id: g.id, did: String(did),
      });
      if (!ok) return;
      renderRooms(); renderGrid(); syncDrawer(did);
    };
    gp.appendChild(b);
  }
  body.appendChild(gp);

  // 历史趋势：可切 6 小时 / 24 小时 / 7 天
  const hist = document.createElement("div");
  hist.className = "dr-history-host";
  hist.appendChild(CardTypes.historyBlock(
    d, state.history[did] || {}, state.drawerHours,
    (h) => { state.drawerHours = h; loadDrawerHistory(did); }));
  body.appendChild(hist);
}

/* ---------------- 场景 ---------------- */
async function loadScenes() {
  if (!state.logged) return;
  try {
    const r = await api("/api/scenes");
    const panel = $("#scene-panel");
    const row = $("#scene-list");
    row.innerHTML = "";
    const items = r.scenes || [];
    if (!r.ok || !items.length) {
      panel.classList.add("hidden");
      return;
    }
    panel.classList.remove("hidden");
    applyMainTab();
    for (const s of items) {
      const b = document.createElement("button");
      b.className = "scene-btn";
      b.textContent = s.name;
      b.onclick = async () => {
        b.disabled = true;
        const res = await api("/api/scenes/run", {
          scene_id: s.scene_id, home_id: s.home_id,
          owner_uid: s.owner_uid, name: s.name,
        });
        b.disabled = false;
        toast(res.ok ? "场景已执行：" + s.name : (res.error || "场景执行失败"));
        loadEvents();
      };
      row.appendChild(b);
    }
  } catch (e) { /* 场景失败不打扰主流程 */ }
}

/* ---------------- ⑤ 自动化 ----------------
 * GetSceneList(scene_type=1) 返回米家 App 的自动化，与上面的手动场景分开。
 * AppSceneService/Edit（flat 包装）承担改名、启停与新建：新建时不带 scene_id，
 * 且必须复制一条有效触发/动作的现有自动化；删除走 AppSceneService/Delete。
 * 三条写入链路都在信地做过受控测试，前端每次写入都要求二次确认，
 * 删除还要求手动输入完整名称复核。
 */
async function loadAutomations(force = false) {
  if (!state.logged) return;
  try {
    const r = await api("/api/automations" + (force ? "?force=1" : ""));
    if (!r.ok) return;
    state.automations = r.automations || [];
    state.autoCount = r.count || 0;
    state.autoEnabled = r.enabled || 0;
    state.autoWritable = !!r.writable;
    state.autoCreateSupported = !!r.create_supported;
    state.autoDeleteSupported = !!r.delete_supported;
  } catch (e) { /* 自动化读取失败不打扰主流程 */ }
  renderAutomations();
}

function renderAutomations() {
  const panel = $("#automation-panel");
  const list = $("#automation-list");
  if (!panel || !list) return;
  list.innerHTML = "";
  if (!state.automations.length) {
    panel.classList.add("hidden");
    return;
  }
  panel.classList.remove("hidden");
  applyMainTab();
  $("#auto-count").textContent = state.autoCount + " 条 · 启用 " + state.autoEnabled;
  const canCreate = state.autoCreateSupported;
  $("#auto-new").classList.toggle("hidden", !canCreate);
  $("#auto-create").classList.toggle(
    "hidden", !(state.autoCreateOpen && canCreate));
  if (state.autoCreateOpen && canCreate) fillCreateTemplates();

  const byHome = new Map();
  for (const a of state.automations) {
    if (!byHome.has(a.home_name)) byHome.set(a.home_name, []);
    byHome.get(a.home_name).push(a);
  }
  for (const [home, items] of byHome) {
    list.appendChild(createEl("div", "auto-home", home + " · " + items.length + " 条"));
    for (const a of items) list.appendChild(autoItem(a));
  }
}

/* 模板下拉：只列含有效触发与动作的自动化（空触发会被云端拒绝）。
 * 用 scene_id 签名判断是否需要重建，避免刷新列表时清空用户已填的表单。 */
function fillCreateTemplates() {
  const sel = $("#auto-new-template");
  if (!sel) return;
  const usable = state.automations.filter(
    (a) => a.counts.trigger > 0 && a.counts.action > 0);
  const sig = usable.map((a) => a.scene_id).join("|");
  if (sig === state.autoTemplateSig) return;
  state.autoTemplateSig = sig;
  const prev = sel.value;
  sel.innerHTML = "";
  if (!usable.length) {
    const o = createEl("option", "", "没有可用模板（需含触发与动作）");
    o.value = "";
    sel.appendChild(o);
  } else {
    const byHome = new Map();
    for (const a of usable) {
      if (!byHome.has(a.home_name)) byHome.set(a.home_name, []);
      byHome.get(a.home_name).push(a);
    }
    for (const [home, items] of byHome) {
      const g = document.createElement("optgroup");
      g.label = home;
      for (const a of items) {
        const o = createEl("option", "",
          (a.enable ? "启用 · " : "停用 · ") + a.name);
        o.value = a.scene_id;
        g.appendChild(o);
      }
      sel.appendChild(g);
    }
    if (prev && usable.some((a) => a.scene_id === prev)) sel.value = prev;
  }
  $("#auto-create-submit").disabled = !usable.length;
}

function createFormPayload() {
  return {
    template_scene_id: ($("#auto-new-template") || {}).value || "",
    name: ($("#auto-new-name").value || "").trim(),
    enable: !!$("#auto-new-enable").checked,
  };
}

/* 只在本地生成完整 payload，不发云端请求，供创建前核对。 */
async function previewCreateAutomation() {
  const out = $("#auto-create-out");
  const p = createFormPayload();
  if (!p.name || !p.template_scene_id) {
    out.textContent = "请先填写名称并选择模板，再预览将要发送的请求。";
    return;
  }
  out.textContent = "正在生成本地预览…";
  let r;
  try {
    r = await api("/api/automations/create/preview", p);
  } catch (e) {
    r = { ok: false, error: String(e) };
  }
  out.textContent = r.ok ? JSON.stringify(r.preview, null, 2)
                         : "预览生成失败：" + (r.error || "未知错误");
}

/* 真实新建：二次确认 → confirm=true 写入 → 强制从云端刷新。 */
async function submitCreateAutomation() {
  const out = $("#auto-create-out");
  const p = createFormPayload();
  if (!p.name) { toast("请先填写名称"); return; }
  if (!p.template_scene_id) { toast("请选择模板"); return; }
  const tpl = state.automations.find((a) => a.scene_id === p.template_scene_id);
  const tip = "将复制「" + (tpl ? tpl.name : p.template_scene_id) +
    "」的触发、条件与动作，新建一条自动化：\n\n" +
    "名称：" + p.name + "\n状态：" + (p.enable ? "立即启用" : "停用（推荐）") +
    "\n\n改动会同步到米家 App 与家庭共享成员，确认创建？";
  if (!window.confirm(tip)) return;
  out.textContent = "正在写入米家云端…";
  let r;
  try {
    r = await api("/api/automations/create", { ...p, confirm: true });
  } catch (e) {
    r = { ok: false, error: String(e) };
  }
  if (!r.ok) {
    out.textContent = "创建失败：" + (r.error || "未知错误");
    toast("自动化创建失败");
    return;
  }
  out.textContent = "创建成功，云端返回：" + JSON.stringify(r.result) +
    "\n新 scene_id：" + (r.created_id || "（云端未返回）");
  toast("自动化已创建");
  $("#auto-new-name").value = "";
  $("#auto-new-enable").checked = false;
  await loadAutomations(true);
  const sid = r.created_id ? String(r.created_id) : "";
  if (sid && state.automations.some((a) => a.scene_id === sid)) {
    await openAutomationDrawer(sid);
  }
}

function autoItem(a) {
  const el = createEl("div", "auto-item " + (a.enable ? "on" : "off"));
  el.appendChild(createEl("span", "auto-dot"));
  const main = createEl("div", "auto-main");
  main.appendChild(createEl("div", "auto-name", a.name));
  main.appendChild(createEl("div", "auto-sum", a.summary));
  el.appendChild(main);
  const side = createEl("div", "auto-side");
  side.appendChild(createEl("span", "auto-badge", a.enable ? "已启用" : "已停用"));
  side.appendChild(createEl("span", "auto-meta",
    "触发 " + a.counts.trigger + " · 条件 " + a.counts.condition +
    " · 动作 " + a.counts.action));
  el.appendChild(side);
  el.onclick = () => openAutomationDrawer(a.scene_id);
  return el;
}

async function openAutomationDrawer(sceneId) {
  state.drawerDid = null;
  state.weatherDrawer = false;
  state.autoDrawer = true;
  state.autoSceneId = sceneId;
  $("#dr-name").textContent = "自动化详情";
  $("#drawer").classList.remove("hidden");
  $("#drawer-mask").classList.remove("hidden");
  const body = $("#dr-body");
  body.innerHTML = "";
  body.appendChild(createEl("div", "dim-note", "正在读取自动化详情…"));
  let r;
  try {
    r = await api("/api/automations/detail?scene_id=" + encodeURIComponent(sceneId));
  } catch (e) {
    r = { ok: false };
  }
  if (!state.autoDrawer || state.autoSceneId !== sceneId) return;
  syncAutomationDrawer(r.ok ? r.item : null);
}

function syncAutomationDrawer(item) {
  const body = $("#dr-body");
  body.innerHTML = "";
  if (!item) {
    body.appendChild(createEl("div", "dim-note", "自动化详情读取失败"));
    return;
  }
  const head = createEl("div", "auto-detail-head");
  head.appendChild(createEl("div", "auto-detail-title", item.name));
  let when = "—";
  if (item.update_time) {
    const t = new Date(Number(item.update_time) * 1000);
    if (!isNaN(t.getTime())) when = t.toLocaleString("zh-CN");
  }
  head.appendChild(createEl("div", "dim-note",
    (item.home_name || "") + " · " + (item.enable ? "已启用" : "已停用") +
    " · 更新于 " + when));
  body.appendChild(head);

  const blocks = [
    ["触发", item.triggers], ["条件", item.conditions],
    ["执行", item.actions], ["否则", item.else_actions],
  ];
  for (const [label, arr] of blocks) {
    if (!arr || !arr.length) continue;
    const sec = createEl("div", "auto-sec");
    sec.appendChild(createEl("div", "auto-sec-title", label + " · " + arr.length));
    for (const e of arr) {
      const row = createEl("div", "auto-row");
      row.appendChild(createEl("span", "auto-row-dev", e.device || "—"));
      row.appendChild(createEl("span", "auto-row-name", e.name || e.key || "—"));
      if (e.value !== undefined && e.value !== null && e.value !== "") {
        row.appendChild(createEl("span", "auto-row-val", "值 " + JSON.stringify(e.value)));
      }
      sec.appendChild(row);
    }
    body.appendChild(sec);
  }
  body.appendChild(createEl("div", "auto-summary", item.summary));

  const det = createEl("details", "auto-raw");
  det.appendChild(createEl("summary", "", "查看原始数据（JSON）"));
  const pre = createEl("pre", "");
  pre.textContent = JSON.stringify(item.raw, null, 2);
  det.appendChild(pre);
  body.appendChild(det);

  const edit = createEl("div", "auto-edit");
  edit.appendChild(createEl("div", "auto-sec-title",
    "编辑 · 改名与启停（会真实同步到米家 App）"));
  const row = createEl("div", "ctrl-row");
  row.appendChild(createEl("label", "", "名称"));
  const inp = createEl("input", "text-input");
  inp.value = item.name;
  row.appendChild(inp);
  const saveBtn = createEl("button", "toggle-btn", "保存名称");
  row.appendChild(saveBtn);
  edit.appendChild(row);

  const row2 = createEl("div", "ctrl-row");
  row2.appendChild(createEl("label", "", "状态"));
  const toggleBtn = createEl("button", "toggle-btn",
    item.enable ? "停用此自动化" : "启用此自动化");
  row2.appendChild(toggleBtn);
  const previewBtn = createEl("button", "toggle-btn", "预览请求内容");
  previewBtn.title = "只在本地生成，不会写入米家";
  row2.appendChild(previewBtn);
  edit.appendChild(row2);

  const out = createEl("pre", "auto-payload");
  out.textContent = state.autoWritable
    ? "改完名称或点过启停后，可点「预览请求内容」核对即将发给米家的完整请求；"
      + "这里只本地生成，不会写入。"
    : "写入接口尚未开放，当前只能查看。";
  edit.appendChild(out);
  body.appendChild(edit);

  saveBtn.disabled = !state.autoWritable;
  toggleBtn.disabled = !state.autoWritable;
  previewBtn.onclick = async () => {
    const name = inp.value.trim();
    const patch = (name && name !== item.name) ? { name } : {};
    if (!Object.keys(patch).length) {
      out.textContent =
        "当前没有改动，所以没有要发送的内容。先改名称或点「启用/停用」，再看这里。";
      return;
    }
    out.textContent = "正在生成本地预览…";
    const p = await api("/api/automations/preview", {
      scene_id: item.scene_id, patch,
    });
    out.textContent = p.ok ? JSON.stringify(p.preview, null, 2)
                           : (p.error || "预览生成失败");
  };
  saveBtn.onclick = () => applyAutomation(item, { name: inp.value.trim() }, out);
  toggleBtn.onclick = () => applyAutomation(item, { enable: !item.enable }, out);
  if (state.autoDeleteSupported) body.appendChild(autoDeleteSection(item));
}

/* 删除区独立成块：名称复核输入框 + 本地 payload 预览 + 二次确认。 */
function autoDeleteSection(item) {
  const box = createEl("div", "auto-danger");
  box.appendChild(createEl("div", "auto-sec-title", "危险操作 · 删除（不可撤销）"));
  box.appendChild(createEl("div", "auto-danger-text",
    "删除会同步到米家 App 与家庭共享成员，无法恢复。请先完整输入该自动化名称作为复核。"));
  const row = createEl("div", "ctrl-row");
  row.appendChild(createEl("label", "", "复核"));
  const inp = createEl("input", "text-input");
  inp.placeholder = item.name;
  row.appendChild(inp);
  const prevBtn = createEl("button", "toggle-btn", "预览请求内容");
  prevBtn.title = "只在本地生成，不会删除";
  const delBtn = createEl("button", "toggle-btn danger-btn", "删除此自动化");
  row.appendChild(prevBtn);
  row.appendChild(delBtn);
  box.appendChild(row);
  const out = createEl("pre", "auto-payload");
  box.appendChild(out);
  prevBtn.onclick = async () => {
    out.textContent = "正在本地生成…";
    let r;
    try {
      r = await api("/api/automations/delete/preview", {
        scene_id: item.scene_id, name: inp.value.trim(),
      });
    } catch (e) {
      r = { ok: false, error: String(e) };
    }
    out.textContent = r.ok ? JSON.stringify(r.preview, null, 2)
                           : "生成失败：" + (r.error || "未知错误");
  };
  delBtn.onclick = () => deleteAutomation(item, inp.value.trim(), out);
  return box;
}

async function deleteAutomation(item, name, out) {
  if (name !== item.name) {
    toast("名称复核不一致，请完整输入自动化名称");
    return;
  }
  if (!window.confirm("将永久删除自动化「" + item.name + "」？\n\n" +
      "此操作不可撤销，米家 App 与家庭共享成员处都会消失。")) return;
  out.textContent = "正在从米家云端删除…";
  let r;
  try {
    r = await api("/api/automations/delete", {
      scene_id: item.scene_id, name, confirm: true,
    });
  } catch (e) {
    r = { ok: false, error: String(e) };
  }
  if (!r.ok) {
    out.textContent = "删除失败：" + (r.error || "未知错误");
    toast("自动化删除失败");
    return;
  }
  toast("自动化已删除");
  $("#dr-close").click();
  await loadAutomations(true);
}

/* 真实写入云端：先二次确认，再发 confirm=true 的 apply 请求。 */
async function applyAutomation(item, patch, out) {
  if (!state.autoWritable) return;
  if (patch.name !== undefined) {
    if (!patch.name) { toast("名称不能为空"); return; }
    if (patch.name === item.name) { toast("名称没有变化"); return; }
    if (!window.confirm("把自动化名称改为「" + patch.name + "」并同步到米家云端？")) return;
  } else if (patch.enable !== undefined) {
    const word = patch.enable ? "启用" : "停用";
    if (!window.confirm(word + "这条自动化？改动会同步到米家 App 和家人设备。")) return;
  }
  out.textContent = "正在写入米家云端…";
  let r;
  try {
    r = await api("/api/automations/apply", {
      scene_id: item.scene_id, patch, confirm: true,
    });
  } catch (e) {
    r = { ok: false, error: String(e) };
  }
  if (!r.ok) {
    out.textContent = "写入失败：" + (r.error || "未知错误");
    toast("自动化写入失败");
    return;
  }
  out.textContent = "写入成功，云端返回：" + JSON.stringify(r.result) +
    "\n改动内容：" + JSON.stringify(r.preview.changes, null, 2);
  toast("自动化已更新");
  await loadAutomations(true);
  if (state.autoDrawer && state.autoSceneId === item.scene_id) {
    await openAutomationDrawer(item.scene_id);
  }
}

/* ---------------- 事件流 ---------------- */
async function loadEvents() {
  try {
    const r = await api("/api/events");
    const ul = $("#event-list");
    ul.innerHTML = "";
    for (const e of r.events || []) {
      const li = document.createElement("li");
      if (e.type === "error") li.className = "err";
      // 全部走 textContent，杜绝设备名里的特殊字符注入 HTML
      const t = document.createElement("span");
      t.className = "t";
      t.textContent = e.time;
      li.appendChild(t);
      li.appendChild(document.createTextNode(
        (e.name ? "[" + e.name + "] " : "") + e.text));
      ul.appendChild(li);
    }
  } catch (e) { /* ignore */ }
}

/* ---------------- 顶栏按钮 ---------------- */
$("#btn-login").onclick = async () => {
  const u = $("#lu").value.trim(), p = $("#lp").value;
  if (!u || !p) { $("#login-msg").textContent = "请填写账号和密码"; return; }
  $("#login-msg").textContent = "登录中…";
  const r = await api("/api/login", { username: u, password: p });
  if (r.ok) {
    $("#login-msg").textContent = "";
    onLoginSuccess();
  } else {
    $("#login-msg").textContent = r.error || "登录失败";
    $("#otp-box").classList.remove("hidden");
  }
};

$("#btn-otp").onclick = async () => {
  await api("/api/otp", { code: $("#otp").value.trim() });
  toast("验证码已提交，请稍候再刷新");
};

$("#btn-logout").onclick = async () => {
  await api("/api/logout", {});
  state.devices = {}; state.live = {};
  await loadDevices();
  toast("已退出登录");
};

$("#btn-refresh").onclick = async () => {
  toast("刷新中…");
  await api("/api/devices/refresh", {});
  await loadDevices();
};

$("#dr-close").onclick = () => {
  state.drawerDid = null;
  state.weatherDrawer = false;
  state.autoDrawer = false;
  state.autoSceneId = null;
  $("#drawer").classList.add("hidden");
  $("#drawer-mask").classList.add("hidden");
};
$("#drawer-mask").onclick = () => $("#dr-close").click();

$("#search").oninput = (e) => {
  state.kw = (e.target.value || "").toLowerCase();
  renderGrid();
};

$$("#main-tabs .tab").forEach((b) => {
  b.onclick = () => {
    state.mainTab = b.dataset.tab;
    localStorage.setItem("mi-main-tab", state.mainTab);
    applyMainTab();
  };
});

$("#auto-new").onclick = () => {
  state.autoCreateOpen = !state.autoCreateOpen;
  renderAutomations();
};
$("#auto-create-preview").onclick = previewCreateAutomation;
$("#auto-create-submit").onclick = submitCreateAutomation;
$("#auto-refresh").onclick = async (e) => {
  const btn = e.currentTarget;
  btn.disabled = true;
  await loadAutomations(true);
  btn.disabled = false;
  toast("自动化列表已刷新");
};

/* ---------------- 启动 ---------------- */
async function waitForRestore() {
  /* 启动时后台线程可能正在用本机 token 恢复登录：
   * - 已登录 → 立即进主界面
   * - 后端明确不在恢复中（无 token / 已失败）→ 立即展示登录页，不再等待
   * - 恢复中 → 最多等 6 秒，避免登录页一闪而过又跳回主界面 */
  for (let i = 0; i < 12; i++) {
    try {
      const r = await api("/api/status");
      if (r.logged_in) return true;
      if (!r.restoring) return false;
    } catch (e) { /* ignore */ }
    await new Promise((res) => setTimeout(res, 500));
  }
  return false;
}

(async function init() {
  // 登录页的小猫：先装好再进流程，后面 setQrStatus 才有人接心情
  if (typeof LoginCat !== "undefined") {
    LoginCat.install({ mount: $("#lp-cat-host") });
  }
  // 旧版本只存了 mi-theme（dark/light），迁移到新主题系统
  if (!localStorage.getItem("mi-mode") && localStorage.getItem("mi-theme")) {
    THEME.mode = localStorage.getItem("mi-theme") === "dark" ? "dark" : "light";
  }
  applyTheme();
  bindThemePop();
  loadWeather();
  await waitForRestore();
  await loadDevices();
  await loadLayout();
  applyMainTab();
  if (state.logged) {
    await loadEvents();
    loadScenes();
    loadAutomations();
    pollFull();
  }
  setInterval(pollQuick, 3000);      // 3 秒开关跟随（未实现项 #6）
  setInterval(pollFull, 45000);
  setInterval(loadEvents, 15000);
  setInterval(loadWeather, 600000);
  setInterval(loadScenes, 300000);   // 场景列表 5 分钟刷一次
  setInterval(loadAutomations, 300000);
})();
