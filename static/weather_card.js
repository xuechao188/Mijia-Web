/* ④ 天气卡片：把顶部固定横幅换成网格里的一张卡。
 *
 * 与设备卡共用同一套 grid / sz-sm|md|lg 排版，但内容按尺寸递增：
 *   sm 城市 + 温度 + 天气
 *   md + 体感 / 今日高低温 / AQI / 风速
 *   lg + 湿度 / 降水 / 日出日落 / 24 小时温度曲线
 * 点开抽屉看完整读数、逐小时预报，并可切换城市与卡片尺寸。
 *
 * 纯函数（kindOf / iconSvg / aqiGrade / fieldsFor / tempText /
 * hourlySeries / tempRange）无 DOM 依赖，Node 可直接测；
 * DOM 部分只用 createElement + appendChild，便于 DOM 桩回归。
 */
(function (root) {
  "use strict";

  var SIZES = ["sm", "md", "lg"];
  var SIZE_LABELS = { sm: "小", md: "中", lg: "大" };

  // WMO weather code -> 图标种类
  function kindOf(code) {
    var c = Number(code);
    if (c === 0 || c === 1) return "sun";
    if (c === 2) return "partly";
    if (c === 3) return "cloud";
    if (c === 45 || c === 48) return "fog";
    if ((c >= 51 && c <= 67) || (c >= 80 && c <= 82)) return "rain";
    if ((c >= 71 && c <= 77) || c === 85 || c === 86) return "snow";
    if (c === 95 || c === 96 || c === 99) return "storm";
    return "cloud";
  }

  var ICONS = {
    sun: '<circle cx="12" cy="12" r="4"/>' +
         '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4' +
         'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    partly: '<circle cx="8" cy="8" r="3"/>' +
            '<path d="M8 1v1.5M2.5 8H1M3.4 3.4l1 1"/>' +
            '<path d="M7 18h10a3.5 3.5 0 0 0 .3-7 5 5 0 0 0-9.5 1.2A3.4 3.4 0 0 0 7 18z"/>',
    cloud: '<path d="M6 18h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 18z"/>',
    rain: '<path d="M6 15h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 15z"/>' +
          '<path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"/>',
    snow: '<path d="M6 15h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 15z"/>' +
          '<path d="M8 19h.01M12 20h.01M16 19h.01"/>',
    fog: '<path d="M5 9h14M3 13h18M6 17h12"/>',
    storm: '<path d="M6 15h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 15z"/>' +
           '<path d="M13 16l-3 4h3l-1 3"/>',
  };

  function iconSvg(kind, px) {
    var p = ICONS[kind] || ICONS.cloud;
    var n = px || 24;
    return '<svg class="wc-icon" width="' + n + '" height="' + n +
           '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
           'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" ' +
           'aria-hidden="true">' + p + '</svg>';
  }

  // Open-Meteo 给的是欧洲 AQI，按欧标分档（不要套中国 AQI 阈值）
  function aqiGrade(aqi) {
    if (aqi === null || aqi === undefined || aqi === "" || !isFinite(Number(aqi))) {
      return { level: 0, label: "--", text: "AQI --" };
    }
    var v = Number(aqi);
    var bands = [[20, "优"], [40, "良"], [60, "中等"],
                 [80, "较差"], [100, "差"]];
    var i, label = "很差", level = 6;
    for (i = 0; i < bands.length; i++) {
      if (v <= bands[i][0]) { label = bands[i][1]; level = i + 1; break; }
    }
    return { level: level, label: label,
             text: "AQI " + Math.round(v) + " · " + label };
  }

  // 每种尺寸允许出现的信息块；渲染时严格按这张表裁剪
  var FIELDS = {
    sm: ["temp", "text"],
    md: ["temp", "text", "feels", "range", "aqi", "wind"],
    lg: ["temp", "text", "feels", "range", "aqi", "wind",
         "humidity", "pop", "sun", "hourly"],
  };
  function fieldsFor(size) { return (FIELDS[size] || FIELDS.md).slice(); }

  function tempText(v, digits) {
    if (v === null || v === undefined || v === "" || !isFinite(Number(v))) return "--";
    return Number(v).toFixed(digits === undefined ? 0 : digits);
  }

  function pctText(v) {
    if (v === null || v === undefined || v === "" || !isFinite(Number(v))) return "--";
    return Math.round(Number(v)) + "%";
  }

  // sparkline 要的是 [[x,y],...]；x 用序号，标签由 hourlyLabels 给
  function hourlySeries(w) {
    var out = [];
    var h = (w && w.hourly) || [];
    for (var i = 0; i < h.length; i++) {
      var v = h[i] && h[i].temp;
      if (v !== null && v !== undefined && isFinite(Number(v))) {
        out.push([i, Number(v)]);
      }
    }
    return out;
  }
  function hourlyLabels(w) {
    var h = (w && w.hourly) || [];
    return [h.length ? (h[0].time || "") : "",
            h.length ? (h[h.length - 1].time || "") : ""];
  }
  function tempRange(w) {
    var pts = hourlySeries(w);
    if (!pts.length) return { min: null, max: null };
    var vals = pts.map(function (p) { return p[1]; });
    return { min: Math.min.apply(null, vals), max: Math.max.apply(null, vals) };
  }

  // ---------------------------------------------------------------- DOM 部分
  function el(doc, tag, cls, text) {
    var e = doc.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined && text !== null) e.textContent = text;
    return e;
  }
  function fill(node, html) { node.innerHTML = html; return node; }
  function stop(e) { if (e && e.stopPropagation) e.stopPropagation(); }

  function num(doc, k, v, extra) {
    var cell = el(doc, "div", "wc-metric" + (extra ? " " + extra : ""));
    cell.appendChild(el(doc, "span", "wc-metric-k", k));
    cell.appendChild(el(doc, "span", "wc-metric-v", v));
    return cell;
  }

  function sizePicker(doc, size, onSize, cls) {
    var box = el(doc, "div", "wc-sizes " + (cls || ""));
    SIZES.forEach(function (s) {
      var b = el(doc, "button", "wc-size" + (s === size ? " active" : ""),
                 SIZE_LABELS[s]);
      b.title = (s === "sm" ? "小卡" : s === "md" ? "中卡" : "大卡");
      b.onclick = function (e) { stop(e); onSize(s); };
      box.appendChild(b);
    });
    return box;
  }

  function metricsBlock(doc, w, fields) {
    var box = el(doc, "div", "wc-metrics");
    var today = (w && w.today) || {};
    var g = aqiGrade(w && w.aqi);
    var rows = [
      ["feels", "体感", tempText(w && w.feels, 0) + "°"],
      ["range", "今日", tempText(today.tmin, 0) + " / " + tempText(today.tmax, 0) + "°"],
      ["aqi", "空气", g.label],
      ["wind", "风速", tempText(w && w.wind, 0) + " km/h"],
      ["humidity", "湿度", pctText(w && w.humidity)],
      ["pop", "降水", pctText(today.pop_max)],
      ["sun", "日照", (today.sunrise || "--") + "–" + (today.sunset || "--")],
    ];
    rows.forEach(function (r) {
      if (fields.indexOf(r[0]) >= 0) box.appendChild(num(doc, r[1], r[2]));
    });
    return box;
  }

  function curveBlock(doc, w, h, tall) {
    var wrap = el(doc, "div", "wc-chart");
    var pts = hourlySeries(w);
    if (!pts.length) {
      wrap.appendChild(el(doc, "div", "ct-chart-empty", "暂无逐时预报数据"));
      return wrap;
    }
    var labels = hourlyLabels(w);
    var cap = el(doc, "div", "ct-chart-cap");
    cap.appendChild(el(doc, "span", "", "未来 " + (w.hourly || []).length + " 小时 · " +
                                        labels[0] + " 起"));
    cap.appendChild(el(doc, "span", "ct-chart-last",
                       tempText(tempRange(w).min, 0) + "° / " +
                       tempText(tempRange(w).max, 0) + "°"));
    wrap.appendChild(cap);
    var svg = el(doc, "div", "ct-chart-svg" + (tall ? " tall" : ""));
    var draw = h.sparkline || function () { return ""; };
    svg.innerHTML = draw(pts, { w: tall ? 320 : 240, h: tall ? 68 : 48,
                                color: "var(--accent)" });
    wrap.appendChild(svg);
    var foot = el(doc, "div", "ct-chart-cap");
    foot.appendChild(el(doc, "span", "", labels[0]));
    foot.appendChild(el(doc, "span", "", labels[1]));
    wrap.appendChild(foot);
    return wrap;
  }

  /** 网格里的天气卡。h = {onSize, onOpen, sparkline, doc} */
  function render(w, size, h) {
    h = h || {};
    var doc = h.doc || root.document;
    size = SIZES.indexOf(size) >= 0 ? size : "md";
    // 拿不到天气数据时保留卡片骨架（而不是整块消失），只显示占位信息
    var fields = (w && w.unavailable) ? FIELDS.sm.slice() : fieldsFor(size);
    var kind = kindOf(w && w.code);
    var e = el(doc, "div", "device-card weather-card sz-" + size +
               " cat-weather wc-" + kind +
               ((w && w.is_day === 0) ? " wc-night" : ""));
    if (e.dataset) e.dataset.widget = "weather";

    var head = el(doc, "div", "wc-head");
    var glyph = el(doc, "span", "wc-glyph");
    fill(glyph, iconSvg(kind, 22));
    head.appendChild(glyph);
    head.appendChild(el(doc, "span", "wc-city", (w && w.city) || "天气"));
    // 小卡只留城市，不放「天气」标签，避免和尺寸按钮挤在一起
    if (size !== "sm" && fields.indexOf("text") >= 0) {
      head.appendChild(el(doc, "span", "wc-tag",
                          (w && w.unavailable) ? "暂不可用" : "天气"));
    }
    head.appendChild(sizePicker(doc, size, h.onSize || function () {}, "in-card"));
    e.appendChild(head);

    var primary = el(doc, "div", "wc-primary");
    primary.appendChild(el(doc, "span", "wc-temp",
                           tempText(w && w.temp, 0) + "°"));
    primary.appendChild(el(doc, "span", "wc-text", (w && w.text) || "--"));
    e.appendChild(primary);

    if (size !== "sm") {
      var mb = metricsBlock(doc, w, fields);
      if (mb.children.length) e.appendChild(mb);
    }
    if (fields.indexOf("hourly") >= 0) e.appendChild(curveBlock(doc, w, h, false));

    var foot = el(doc, "div", "wc-foot");
    foot.appendChild(el(doc, "span", "",
      (w && w.unavailable) ? "天气暂不可用 · 稍后自动重试" :
      (w && w.stale) ? "数据未更新" :
      ((w && w.updated) ? "更新于 " + w.updated : "")));
    foot.appendChild(el(doc, "span", "wc-more", "详情 ›"));
    e.appendChild(foot);

    e.onclick = h.onOpen || function () {};
    return e;
  }

  /** 抽屉：完整读数 + 逐小时列表 + 城市/尺寸设置。h = {onSize, onCity, sparkline, doc} */
  function drawer(w, size, h) {
    h = h || {};
    var doc = h.doc || root.document;
    var wrap = el(doc, "div", "wc-drawer");
    var kind = kindOf(w && w.code);
    var today = (w && w.today) || {};

    var hero = el(doc, "div", "wc-hero");
    var g = el(doc, "span", "wc-glyph big");
    fill(g, iconSvg(kind, 40));
    hero.appendChild(g);
    var ht = el(doc, "div", "wc-hero-text");
    ht.appendChild(el(doc, "div", "wc-hero-temp",
                      tempText(w && w.temp, 0) + "°"));
    ht.appendChild(el(doc, "div", "wc-hero-sub",
                      ((w && w.city) || "") + " · " + ((w && w.text) || "--") +
                      " · 体感 " + tempText(w && w.feels, 0) + "°"));
    hero.appendChild(ht);
    wrap.appendChild(hero);

    var grid = el(doc, "div", "dr-readouts");
    var rows = [
      ["今日最高", tempText(today.tmax, 0) + "°", true],
      ["今日最低", tempText(today.tmin, 0) + "°"],
      ["湿度", pctText(w && w.humidity)],
      ["风速", tempText(w && w.wind, 0) + " km/h"],
      ["空气质量", aqiGrade(w && w.aqi).text],
      ["降水概率", pctText(today.pop_max)],
      ["日出", today.sunrise || "--"],
      ["日落", today.sunset || "--"],
    ];
    rows.forEach(function (r) {
      var cell = el(doc, "div", "dr-readout" + (r[2] ? " primary" : ""));
      cell.appendChild(el(doc, "span", "dr-readout-k", r[0]));
      cell.appendChild(el(doc, "span", "dr-readout-v", r[1]));
      grid.appendChild(cell);
    });
    wrap.appendChild(grid);

    var hist = el(doc, "div", "dr-history");
    var hh = el(doc, "div", "dr-history-head");
    hh.appendChild(el(doc, "span", "dr-h-label", "24 小时温度"));
    hh.appendChild(el(doc, "span", "dim-note", (w && w.hourly || []).length + " 个采样点"));
    hist.appendChild(hh);
    hist.appendChild(curveBlock(doc, w, h, true));
    wrap.appendChild(hist);

    var hours = (w && w.hourly) || [];
    if (hours.length) {
      var strip = el(doc, "div", "wc-hours");
      for (var i = 0; i < hours.length; i += 3) {
        var p = hours[i];
        var c = el(doc, "div", "wc-hour");
        c.appendChild(el(doc, "span", "wc-hour-t", p.time || ""));
        c.appendChild(el(doc, "span", "wc-hour-v", tempText(p.temp, 0) + "°"));
        c.appendChild(el(doc, "span", "wc-hour-p", pctText(p.pop)));
        strip.appendChild(c);
      }
      wrap.appendChild(strip);
    }

    var set = el(doc, "div", "wc-settings");
    var cityRow = el(doc, "div", "ctrl-row");
    cityRow.appendChild(el(doc, "label", "", "天气城市"));
    var inp = el(doc, "input", "text-input");
    inp.value = (w && w.city) || "";
    inp.placeholder = "留空使用服务器默认城市";
    var save = el(doc, "button", "toggle-btn", "保存");
    save.onclick = function () {
      if (h.onCity) h.onCity((inp.value || "").trim());
    };
    var reset = el(doc, "button", "toggle-btn", "恢复默认");
    reset.onclick = function () { if (h.onCity) h.onCity(""); };
    var refresh = el(doc, "button", "toggle-btn", "刷新天气");
    refresh.onclick = function () { if (h.onRetry) h.onRetry(); };
    cityRow.appendChild(inp); cityRow.appendChild(save);
    cityRow.appendChild(reset); cityRow.appendChild(refresh);
    set.appendChild(cityRow);

    var sizeRow = el(doc, "div", "ctrl-row");
    sizeRow.appendChild(el(doc, "label", "", "卡片尺寸"));
    sizeRow.appendChild(sizePicker(doc, size, h.onSize || function () {}, "in-drawer"));
    set.appendChild(sizeRow);
    set.appendChild(el(doc, "div", "dim-note wc-note",
      "数据来源 Open-Meteo · 10 分钟刷新 · 空气质量采用欧洲 AQI 标准"));
    wrap.appendChild(set);
    return wrap;
  }

  var API = {
    SIZES: SIZES, SIZE_LABELS: SIZE_LABELS,
    kindOf: kindOf, iconSvg: iconSvg, aqiGrade: aqiGrade,
    fieldsFor: fieldsFor, tempText: tempText, pctText: pctText,
    hourlySeries: hourlySeries, hourlyLabels: hourlyLabels,
    tempRange: tempRange, render: render, drawer: drawer,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.WeatherCard = API;
})(typeof window !== "undefined" ? window : globalThis);
