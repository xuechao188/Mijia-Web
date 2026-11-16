/* ③ 分类卡片：不同设备长不同的卡片，点开抽屉有更详细的操作。
 *
 * 设计：不重写整张卡，而是在 baseCard 之上「装饰」——开关、名称、
 * 定时按钮、多键开关全部复用，分类只负责追加读数、专属控件、趋势曲线。
 * 读数/曲线是通用能力：插排、屏显开关即使归类为插座/开关，也照样显示温湿度。
 *
 * 纯函数（labelOf / formatValue / productLabel / switchLabel /
 * readoutEntries / curveEntries / sparkline）无 DOM 依赖，Node 可直接测。
 */
(function (root) {
  "use strict";

  // 读数中文名 / 单位 / 精度；单位优先取 spec 给的 unit（见 unitOf）
  var READOUTS = {
    temperature: { label: "温度", unit: "°C", digits: 1, order: 1 },
    humidity: { label: "湿度", unit: "%", digits: 0, order: 2 },
    power: { label: "功率", unit: "W", digits: 1, order: 3 },
    voltage: { label: "电压", unit: "V", digits: 1, order: 4 },
    current: { label: "电流", unit: "A", digits: 2, order: 5 },
    illumination: { label: "照度", unit: "lx", digits: 0, order: 6 },
    battery_level: { label: "电量", unit: "%", digits: 0, order: 7 },
    filter_life: { label: "滤芯", unit: "%", digits: 0, order: 8 },
    "pm2.5-density": { label: "PM2.5", unit: "μg/m³", digits: 0, order: 9 },
    "co2-density": { label: "CO₂", unit: "ppm", digits: 0, order: 10 },
    brightness: { label: "亮度", unit: "%", digits: 0, order: 11 },
    "color-temperature": { label: "色温", unit: "K", digits: 0, order: 12 },
    "target-temperature": { label: "目标温度", unit: "°C", digits: 0, order: 13 },
    "fan-level": { label: "风速", unit: "", digits: 0, order: 14 },
    "speed-level": { label: "风速", unit: "%", digits: 0, order: 15 },
    volume: { label: "音量", unit: "%", digits: 0, order: 16 },
    "off-delay-time": { label: "延时关机", unit: "分", digits: 0, order: 17 },
    mode: { label: "模式", unit: "", digits: 0, order: 18 },
    motion: { label: "人体", unit: "", digits: 0, order: 19, bool: ["无人", "有人"] },
    contact: { label: "门窗", unit: "", digits: 0, order: 20, bool: ["闭合", "断开"] },
    "vertical-swing": { label: "上下摆风", unit: "", digits: 0, order: 21, bool: ["关", "开"] },
    "horizontal-swing": { label: "左右摇头", unit: "", digits: 0, order: 22, bool: ["关", "开"] },
  };

  // 与 cards.js 的 CURVE_KEYS 保持一致（Node 里没有 window.Cards 时用这份）
  var CURVE_KEYS = [
    "temperature", "humidity", "illumination", "power", "voltage",
    "current", "filter_life", "pm2.5-density", "co2-density",
  ];

  var UNIT_MAP = {
    celsius: "°C", percentage: "%", lux: "lx", watt: "W",
    volt: "V", ampere: "A", kelvin: "K", minutes: "分",
  };

  // spec 的 description 是英文显示名，这里翻成中文（只影响展示，不改云端）
  var PRODUCT_RULES = [
    [/温湿度|humidity|thermo|hygro/i, "温湿度计"],
    [/water.?puri|净水/i, "净水器"],
    [/air.?fryer|fryer|空气炸/i, "空气炸锅"],
    [/hood|油烟/i, "吸油烟机"],
    [/washer|洗衣/i, "洗衣机"],
    [/three.?key|三键|三开/i, "三键开关"],
    [/two.?key|双键/i, "双键开关"],
    [/wall.?switch|墙壁开关|switch service/i, "墙壁开关"],
    [/vacuum|robot|扫地/i, "扫地机器人"],
    [/purifier|净化/i, "净化器"],
    [/camera|摄像/i, "摄像机"],
    [/lock|门锁/i, "智能门锁"],
    [/curtain|窗帘/i, "窗帘电机"],
    [/router|路由/i, "路由器"],
    [/gateway|网关/i, "网关"],
    [/repeater|放大器/i, "信号放大器"],
    [/plug|socket|插座|插排/i, "智能插座"],
    [/temperature.?humidity|温湿度/i, "温湿度计"],
    [/motion.?sensor|人体/i, "人体传感器"],
    [/occupancy|存在传感器/i, "存在传感器"],
    [/gas.?sensor|燃气/i, "燃气传感器"],
    [/sensor|传感器/i, "传感器"],
    [/remote.?control|红外遥控/i, "红外遥控器"],
    [/speaker|音箱/i, "智能音箱"],
    [/video.?doorbell|可视门铃/i, "可视门铃"],
    [/toothbrush|牙刷/i, "电动牙刷"],
    [/watch|hand.?band|手表|手环/i, "智能穿戴"],
    [/toilet|马桶/i, "智能马桶盖"],
    [/towel.?rack|毛巾架/i, "电热毛巾架"],
    [/bath.?heater|浴霸/i, "浴霸"],
    [/kettle|水壶/i, "电水壶"],
    [/control.?panel|中控屏/i, "智能中控屏"],
    [/mosquito|驱蚊/i, "智能驱蚊器"],
    [/air.?conditioner|空调/i, "空调"],
    [/outlet|插座/i, "智能插座"],
    [/light|灯/i, "智能灯"],
    [/switch|开关/i, "智能开关"],
    [/valve|阀/i, "智能阀门"],
  ];

  function labelOf(key, d) {
    if (READOUTS[key]) return READOUTS[key].label;
    // 冷门控件：至少用 spec 里自带的中文 label，不要把英文 key 露在卡片上
    var ctrls = (d && d.controls) || [];
    for (var i = 0; i < ctrls.length; i++) {
      if (ctrls[i].key === key && ctrls[i].label) return ctrls[i].label;
    }
    return key;
  }

  function unitOf(key, d) {
    var meta = ((d && d.readable) || {})[key];
    var raw = meta && meta.unit;
    if (raw && UNIT_MAP[String(raw).toLowerCase()]) {
      return UNIT_MAP[String(raw).toLowerCase()];
    }
    if (raw && /^[^\w\s]{1,4}$/.test(String(raw))) return raw;  // 已是 °C / % 之类
    for (var i = 0; i < (((d && d.controls) || [])).length; i++) {
      var c = d.controls[i];
      if (c.key === key && c.unit) return c.unit;
    }
    return (READOUTS[key] && READOUTS[key].unit) || "";
  }

  function formatValue(key, v, d) {
    if (v === undefined || v === null) return "";
    var meta = READOUTS[key] || {};
    if (typeof v === "boolean" || meta.bool) {
      return meta.bool ? meta.bool[v ? 1 : 0] : (v ? "开" : "关");
    }
    if (typeof v !== "number" || !isFinite(v)) return String(v);
    var digits = meta.digits === undefined ? 1 : meta.digits;
    var s = v.toFixed(digits);
    if (/\.0+$/.test(s)) s = s.replace(/\.0+$/, "");
    return s + (unitOf(key, d) || "");
  }

  function productLabel(d) {
    var p = ((d && d.product) || "").trim();
    for (var i = 0; i < PRODUCT_RULES.length; i++) {
      if (PRODUCT_RULES[i][0].test(p)) return PRODUCT_RULES[i][1];
    }
    if (p && /[\u4e00-\u9fa5]/.test(p)) return p;   // 本身是中文，保留
    if (p && !/^[a-z0-9._\-\s]+$/i.test(p)) return p;
    return "";   // 纯英文型号不显示，交给「型号」行
  }

  function switchLabel(s, i) {
    var t = String((s && s.label) || "").toLowerCase();
    if (/left|左/.test(t)) return "左键";
    if (/middle|center|中/.test(t)) return "中键";
    if (/right|右/.test(t)) return "右键";
    if (/toggle|切换/.test(t)) return "切换";
    if (/^on\d+$/.test(t) || /switch service|switch$/.test(t)) {
      return "按键 " + (i + 1);
    }
    return (s && s.label) || ("按键 " + (i + 1));
  }

  function pickControl(d, key) {
    for (var i = 0; i < (((d && d.controls) || [])).length; i++) {
      if (d.controls[i].key === key) return d.controls[i];
    }
    return null;
  }

  /** 有实时值的读数，按优先级排序；供卡片/抽屉共用。 */
  // 摄像头/安防参数（夜视、录像模式…）是"控件"而非传感器读数：
  // 不进卡片读数/抽屉读数，只在抽屉控制区按控件呈现，避免出现 "夜视 0" 之类噪声。
  function isCameraCtrl(c) {
    var s = (c && c.svc) || "";
    return s.indexOf("camera-control") >= 0
      || s.indexOf("video-doorbell") >= 0
      || s.indexOf("motion-detection") >= 0;
  }

  function readoutEntries(d, live) {
    var keys = Object.keys((d && d.readable) || {});
    var ctrls = (d && d.controls) || [];
    for (var i = 0; i < ctrls.length; i++) {
      if (ctrls[i].readable && !isCameraCtrl(ctrls[i])
          && keys.indexOf(ctrls[i].key) < 0) keys.push(ctrls[i].key);
    }
    var out = [];
    for (var j = 0; j < keys.length; j++) {
      var k = keys[j];
      if (!Object.prototype.hasOwnProperty.call(live || {}, k)) continue;
      if (live[k] === null || live[k] === undefined) continue;
      var meta = READOUTS[k] || {};
      out.push({
        key: k, label: labelOf(k, d), text: readoutText(d, k, live[k]),
        value: live[k], unit: unitOf(k, d),
        order: meta.order || 90, primary: k === "temperature",
      });
    }
    out.sort(function (a, b) { return a.order - b.order; });
    return out;
  }

  /** 读数文本：枚举控件取选项中文名，避免把「模式」显示成裸数字 0。 */
  function readoutText(d, key, v) {
    var c = pickControl(d, key);
    if (c && c.kind === "enum" && c.options && c.options.length) {
      for (var i = 0; i < c.options.length; i++) {
        if (c.options[i].v === v) return String(c.options[i].t);
      }
    }
    return formatValue(key, v, d);
  }

  /** 有历史点的曲线，按优先级排序。series 形如 {key: [[ts,v], ...]}。 */
  function curveEntries(d, series) {
    var out = [];
    var keys = (root.Cards && root.Cards.CURVE_KEYS) || CURVE_KEYS;
    // 只画这台设备当前确实具备的读数：设备换过 spec / 历史库有残留键时不串图
    var allowed = Object.keys((d && d.readable) || {});
    var ctrls = (d && d.controls) || [];
    for (var a = 0; a < ctrls.length; a++) {
      if (ctrls[a].readable && allowed.indexOf(ctrls[a].key) < 0) {
        allowed.push(ctrls[a].key);
      }
    }
    for (var k in (series || {})) {
      if (!Object.prototype.hasOwnProperty.call(series, k)) continue;
      if (keys.indexOf(k) < 0) continue;
      if (allowed.length && allowed.indexOf(k) < 0) continue;
      var pts = series[k] || [];
      if (pts.length < 2) continue;
      var meta = READOUTS[k] || {};
      out.push({ key: k, label: labelOf(k), points: pts,
                 unit: unitOf(k, d), order: meta.order || 90,
                 last: formatValue(k, pts[pts.length - 1][1], d) });
    }
    out.sort(function (a, b) { return a.order - b.order; });
    return out;
  }

  /** 生成内联 SVG 折线（纯字符串，无 DOM/依赖，卡片与抽屉共用）。 */
  function sparkline(points, opt) {
    opt = opt || {};
    var w = opt.w || 240, h = opt.h || 52, pad = 4;
    var pts = (points || []).filter(function (p) {
      return p && isFinite(p[0]) && isFinite(p[1]);
    });
    if (!pts.length) return "";
    var vals = pts.map(function (p) { return p[1]; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi - lo < 1e-9) { lo -= 1; hi += 1; }
    var span = hi - lo;
    var xy = pts.map(function (p, i) {
      var x = pts.length === 1 ? w / 2 : pad + i / (pts.length - 1) * (w - pad * 2);
      var y = h - pad - (p[1] - lo) / span * (h - pad * 2);
      return [Math.round(x * 10) / 10, Math.round(y * 10) / 10];
    });
    var line = xy.map(function (p) { return p[0] + "," + p[1]; }).join(" ");
    var area = "M" + xy[0][0] + "," + (h - pad) + " L" +
      xy.map(function (p) { return p[0] + "," + p[1]; }).join(" L") +
      " L" + xy[xy.length - 1][0] + "," + (h - pad) + " Z";
    var color = opt.color || "var(--accent)";
    var id = "g" + Math.random().toString(36).slice(2, 8);
    return '<svg class="ct-svg" viewBox="0 0 ' + w + ' ' + h + '" ' +
      'preserveAspectRatio="none" role="img" aria-label="趋势曲线">' +
      '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">' +
      '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.26"/>' +
      '<stop offset="100%" stop-color="' + color + '" stop-opacity="0"/>' +
      '</linearGradient></defs>' +
      '<path d="' + area + '" fill="url(#' + id + ')"/>' +
      '<polyline points="' + line + '" fill="none" stroke="' + color +
      '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<circle cx="' + xy[xy.length - 1][0] + '" cy="' + xy[xy.length - 1][1] +
      '" r="2.6" fill="' + color + '"/></svg>';
  }

  // ---------------------------------------------------------------- DOM 部分
  function el(tag, cls, text) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }

  function stop(e) { e.stopPropagation(); }

  var D = null;   // install 注入的依赖

  function metricNode(entry, big) {
    var box = el("div", "ct-metric" + (big ? " primary" : ""));
    box.appendChild(el("span", "ct-metric-k", entry.label));
    box.appendChild(el("span", "ct-metric-v", entry.text));
    return box;
  }

  function sliderRow(d, c) {
    var live = D.state.live[d.did] || {};
    var row = el("div", "ct-slider-row");
    var head = el("div", "ct-slider-head");
    head.appendChild(el("span", "ct-slider-k", c.label));
    var val = el("span", "ct-slider-v",
      (live[c.key] === undefined || live[c.key] === null
        ? c.min : live[c.key]) + (c.unit || ""));
    head.appendChild(val);
    var inp = document.createElement("input");
    inp.type = "range";
    inp.className = "ct-range";
    inp.min = c.min; inp.max = c.max; inp.step = c.step || 1;
    inp.value = (live[c.key] === undefined || live[c.key] === null
      ? c.min : live[c.key]);
    inp.addEventListener("pointerdown", function (e) { stop(e); D.hold(d.did, true); });
    inp.addEventListener("click", stop);
    inp.oninput = function () { val.textContent = inp.value + (c.unit || ""); };
    inp.onchange = function (e) {
      stop(e);
      D.hold(d.did, false);
      D.setControl(d.did, c, Number(inp.value));
    };
    row.appendChild(head); row.appendChild(inp);
    return row;
  }

  function stepperRow(d, c) {
    var live = D.state.live[d.did] || {};
    var row = el("div", "ct-stepper-row");
    row.appendChild(el("span", "ct-slider-k", c.label));
    var box = el("div", "ct-stepper");
    var cur = (live[c.key] === undefined || live[c.key] === null
      ? c.min : Number(live[c.key]));
    var val = el("span", "ct-stepper-v", cur + (c.unit || ""));
    var minus = el("button", "ct-step", "−");
    var plus = el("button", "ct-step", "+");
    function move(delta) {
      var step = Number(c.step) || 1;
      var next = Math.max(Number(c.min), Math.min(Number(c.max), cur + delta * step));
      if (next === cur) return;
      cur = next;
      val.textContent = cur + (c.unit || "");
      D.setControl(d.did, c, cur);
    }
    minus.onclick = function (e) { stop(e); move(-1); };
    plus.onclick = function (e) { stop(e); move(1); };
    box.appendChild(minus); box.appendChild(val); box.appendChild(plus);
    row.appendChild(box);
    return row;
  }

  /** 按类别挑出「卡片上直接能调」的控件。只有设备真的支持才出现。 */
  function cardControls(d, cat, size) {
    if (size === "sm") return [];
    var out = [];
    if (cat === "light") {
      var br = pickControl(d, "brightness");
      var ct = pickControl(d, "color-temperature");
      if (br && br.writable && br.kind === "range") out.push(br);
      if (size === "lg" && ct && ct.writable && ct.kind === "range") out.push(ct);
    } else if (cat === "climate" || cat === "appliance") {
      var tt = pickControl(d, "target-temperature");
      if (tt && tt.writable && tt.kind === "range") out.push(tt);
      if (size === "lg") {
        var fl = pickControl(d, "fan-level") || pickControl(d, "speed-level");
        if (fl && fl.writable && fl.kind === "range") out.push(fl);
      }
    } else if (cat === "purifier" || cat === "cleaner" || cat === "curtain") {
      var md = pickControl(d, "mode");
      if (size === "lg" && md && md.writable && md.kind === "range") out.push(md);
    }
    return out;
  }

  function decorate(d, size, cat) {
    var e = D.baseCard(d, size);
    e.classList.add("ct-card");
    var live = D.state.live[d.did] || {};
    // 离线设备只保留「图标 + 名称 + 离线」：控件点了也不会成功，
    // 摆在卡片上只会让人以为程序坏了（参考项目的原话）。读数仍保留最后采样值。
    var offline = !d.online;
    var ctrls = offline ? [] : cardControls(d, cat, size);
    var reads = readoutEntries(d, live);
    // 用户自选的「卡片外显值」排到最前，其余按默认优先级；
    // 这样既保留该设置的作用，又不需要在状态行重复一遍读数。
    var picks = (D.metricsOf && D.metricsOf(d.did)) || [];
    if (picks.length) {
      reads.sort(function (a, b) {
        var ai = picks.indexOf(a.key), bi = picks.indexOf(b.key);
        ai = ai < 0 ? 99 : ai; bi = bi < 0 ? 99 : bi;
        return ai !== bi ? ai - bi : a.order - b.order;
      });
    }
    // 滑杆/步进本身已显示当前值，读数区不重复（温度主读数保留）
    if (size !== "sm" && ctrls.length) {
      var shown = ctrls.map(function (c) { return c.key; });
      reads = reads.filter(function (r) {
        return r.primary || shown.indexOf(r.key) < 0;
      });
    }
    // 固定行高后中卡只放得下一块内容：有滑杆就只放滑杆（滑杆自带数值），
    // 否则「读数 + 滑杆」会把卡撑出格子被裁掉
    if (size === "md" && ctrls.length) reads = [];
    // 多键开关已经占掉两行（3 路以上），读数再摆就顶破格子；
    // 而且墙壁开关/中控屏的读数本来价值就低，点开抽屉能看全。
    // 小卡不受影响：sm 的读数只并进副标题，不会撑高。
    if (size !== "sm" && e.querySelector(".dc-switches")) reads = [];
    var curves = offline ? [] : curveEntries(d, (D.state.history[d.did] || {}));

    // 类型信息已由卡片头部的图标 + 类型色表达（device_icons.js），
    // 状态行不再插类别标签——一行只读一件事，扫视时才不打架。
    var sub = e.querySelector(".dc-sub");
    var pl = productLabel(d);
    var rows = e.querySelectorAll(".dc-detail-row");
    for (var i = 0; i < rows.length; i++) {
      var k = rows[i].querySelector(".dc-detail-k");
      var v = rows[i].querySelector(".dc-detail-v");
      if (k && v && k.textContent === "产品" && pl) {
        v.textContent = pl; v.title = pl;
      }
    }
    // 有分类内容时把 4 行设备档案压成一行，给读数/曲线让位
    if (size === "lg" && (reads.length || curves.length || ctrls.length)) {
      var detail = e.querySelector(".dc-detail");
      if (detail) {
        var info = el("div", "ct-info");
        var bits = [pl || D.Cards.CATEGORY_LABELS[cat],
                    [d.home, d.room].filter(Boolean).join(" / ") || "未分配"];
        info.textContent = bits.filter(Boolean).join(" · ");
        detail.parentNode.replaceChild(info, detail);
      }
    }

    // 小卡：只把一项读数并进副标题，避免撑高网格。
    // 只挑「有单位」或「布尔状态」的读数——否则会出现「已关闭 · 0」
    // 这种连标签都没有的尾巴，谁也不知道 0 是什么。
    if (size === "sm") {
      var pick0 = null;
      for (var q = 0; q < reads.length; q++) {
        var rq = reads[q];
        var boolish = (READOUTS[rq.key] && READOUTS[rq.key].bool)
          || typeof rq.value === "boolean";
        if (boolish || rq.unit) { pick0 = rq; break; }
      }
      if (pick0) {
        if (!sub) {
          // 没有状态行的设备（传感器/网关）让读数自己撑起这一行；
          // 这类卡本来就没有开关，不显示读数就只剩一个名字了
          sub = el("div", "dc-sub");
          var titlesEl = e.querySelector(".dc-titles");
          if (titlesEl) titlesEl.appendChild(sub);
        }
        if (sub) {
          var sep = (sub.childNodes && sub.childNodes.length) ? " · " : "";
          sub.appendChild(document.createTextNode(sep + pick0.text));
        }
      }
      return e;
    }

    // 中/大卡：读数区
    if (reads.length) {
      var limit = size === "lg" ? 4 : 2;
      var box = el("div", "ct-readouts");
      for (var j = 0; j < Math.min(limit, reads.length); j++) {
        box.appendChild(metricNode(reads[j], reads[j].primary));
      }
      e.appendChild(box);
    }

    // 专属控件：range 用滑杆，设定温度用步进（比拖 30~230 的滑杆好用）
    if (ctrls.length) {
      var cs = el("div", "ct-controls");
      for (var m = 0; m < ctrls.length; m++) {
        var c = ctrls[m];
        cs.appendChild(c.key === "target-temperature"
          ? stepperRow(d, c) : sliderRow(d, c));
      }
      e.appendChild(cs);
    }

    // 大卡：一条趋势曲线（有滑杆时不画，把高度留给可操作的东西）
    if (size === "lg") {
      var host = e.querySelector(".dc-extra") || e;
      if (curves.length && !ctrls.length) {
        var c0 = curves[0];
        var chart = el("div", "ct-chart");
        var cap = el("div", "ct-chart-cap");
        cap.appendChild(el("span", "", c0.label + "趋势"));
        cap.appendChild(el("span", "ct-chart-last", c0.last));
        chart.appendChild(cap);
        var svg = el("div", "ct-chart-svg");
        svg.innerHTML = sparkline(c0.points, { w: 240, h: 48 });
        chart.appendChild(svg);
        host.appendChild(chart);
      } else if (!offline && !ctrls.length && D.Cards.hasCurve(d)) {
        host.appendChild(el("div", "ct-chart-empty", "历史曲线采样中…"));
      }
    }

    // 收口：除头部以外没有任何「实质内容块」，说明这张卡只剩
    // 「图标 + 名称 + 状态」。尺寸判定只能看「设备声明了什么能力」——
    // 声明有读数但实时值没拿到，或者用户手动设过大卡（layout.json），
    // 都会落进这里。占 2 列甚至 2×2 就是一块空板子，收成单格，
    // 把屏幕位置让给真有内容的设备（点开抽屉仍能看到全部信息）。
    if (size !== "sm") {
      var bare = !e.querySelector(".ct-readouts") && !e.querySelector(".ct-controls")
        && !e.querySelector(".ct-chart") && !e.querySelector(".dc-actions")
        && !e.querySelector(".dc-switches");
      if (bare) {
        e.classList.add("is-bare");
        [".dc-detail", ".dc-extra"].forEach(function (sel) {
          var n = e.querySelector(sel);
          if (n && n.parentNode) n.parentNode.removeChild(n);
        });
      }
    }
    return e;
  }

  /** 抽屉里的历史区：时间范围切换 + 多条曲线。 */
  function historyBlock(d, series, hours, onRange) {
    var wrap = el("div", "dr-history");
    var head = el("div", "dr-history-head");
    head.appendChild(el("span", "dr-h-label", "历史趋势"));
    var ranges = el("div", "dr-h-ranges");
    [[6, "6 小时"], [24, "24 小时"], [168, "7 天"]].forEach(function (r) {
      var b = el("button", "chip" + (Number(hours) === r[0] ? " active" : ""), r[1]);
      b.onclick = function () { onRange(r[0]); };
      ranges.appendChild(b);
    });
    head.appendChild(ranges);
    wrap.appendChild(head);
    var curves = curveEntries(d, series);
    if (!curves.length) {
      wrap.appendChild(el("div", "ct-chart-empty",
        "暂无历史数据，服务运行后会每 5 分钟自动采样一次"));
      return wrap;
    }
    for (var i = 0; i < Math.min(3, curves.length); i++) {
      var c = curves[i];
      var item = el("div", "dr-h-item");
      var cap = el("div", "ct-chart-cap");
      cap.appendChild(el("span", "", c.label + " · 当前 " + c.last));
      var nums = c.points.map(function (p) { return p[1]; });
      cap.appendChild(el("span", "ct-chart-last",
        "最低 " + formatValue(c.key, Math.min.apply(null, nums), d) +
        " / 最高 " + formatValue(c.key, Math.max.apply(null, nums), d)));
      item.appendChild(cap);
      var svg = el("div", "ct-chart-svg tall");
      svg.innerHTML = sparkline(c.points, { w: 320, h: 68 });
      item.appendChild(svg);
      wrap.appendChild(item);
    }
    return wrap;
  }

  function install(renderers, deps) {
    D = deps;
    D.Cards = root.Cards || deps.Cards;
    var cats = ["light", "climate-sensor", "climate", "appliance",
                "purifier", "cleaner", "camera", "curtain",
                "outlet", "switch", "sensor", "hub", "ir", "generic"];
    cats.forEach(function (cat) {
      renderers[cat] = function (d, size) { return decorate(d, size, cat); };
    });
  }

  var API = {
    READOUTS: READOUTS, labelOf: labelOf, formatValue: formatValue,
    productLabel: productLabel, switchLabel: switchLabel,
    pickControl: pickControl, readoutEntries: readoutEntries,
    curveEntries: curveEntries, sparkline: sparkline,
    cardControls: cardControls, historyBlock: historyBlock, install: install,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.CardTypes = API;
})(typeof window !== "undefined" ? window : globalThis);
