/* 设备类别与卡片尺寸判定。
 *
 * 纯函数、无 DOM 依赖：浏览器里挂到 window.Cards，Node 里可直接 require 测试。
 * 判定顺序（③ 修正过，之前「能力优先」会把带温湿度的插排当温度计、
 * 把空气炸锅当空调、把智能门锁当摄像头）：
 *   1) 型号/产品名决定「主功能」——决定卡片长什么样；
 *   2) 能力只在型号认不出时兜底分类；
 *   3) 传感器读数与趋势曲线不属于任何单一类别，作为通用能力叠加，
 *      因此插排、屏显开关照样能显示温湿度和曲线。
 */
(function (root) {
  "use strict";

  var CATEGORY_LABELS = {
    light: "灯光", "climate-sensor": "环境", climate: "空调",
    appliance: "厨电", purifier: "净化", cleaner: "清洁",
    camera: "安防", curtain: "窗帘", outlet: "插座", switch: "开关",
    sensor: "传感器", hub: "网关", ir: "红外遥控", generic: "设备",
  };

  // 有连续变化、适合画趋势曲线的读数键
  var CURVE_KEYS = [
    "temperature", "humidity", "illumination", "power", "voltage",
    "current", "filter_life", "pm2.5-density", "co2-density",
  ];

  // 以「开/关」为主控能力的品类才在卡片与详情里显示电源开关；
  // 网关/音箱/WiFi（hub）、摄像头、传感器、温湿度、净化、清洁等
  // 即使 spec 里带 switch 服务也不应展示电源开关（用户反馈）。
  var TOGGLE_CATS = {
    light: 1, outlet: 1, switch: 1, climate: 1, appliance: 1, curtain: 1,
  };

  var LARGE = ["climate-sensor", "climate", "purifier", "cleaner", "appliance"];
  var MEDIUM = ["light", "camera", "curtain"];

  // 顺序不可随意调整：先具体家电，后泛化关键字（switch/sensor 会吃掉很多型号）
  var MODEL_RULES = [
    // 红外遥控必须排第一：miir.light.* 会被 /light/ 抢走、miir.aircondition.*
    // 会被 /aircondition/ 判成空调，它们其实是遥控器
    [/^miir\.|^ir\.|红外遥控/, "ir"],
    [/sensor_ht|sensor\.ht|thermo|hygro|temp.?humid|miaomiaoce|温湿度/, "climate-sensor"],
    [/acpartner|aircondition|air.?con|空调/, "climate"],
    [/fryer|oven|hood|washer|cooker|microwave|kettle|rice|dishwasher|st701|蒸烤|洗衣|油烟|空气炸/, "appliance"],
    [/purifier|airfresh|new.?wind|waterpuri|新风|净化|净水/, "purifier"],
    [/vacuum|rockrobo|sweeper|robot.?clean|扫地/, "cleaner"],
    [/camera|cateye|loock|lock|doorlock|摄像|猫眼|门锁/, "camera"],
    [/curtain|wcurtain|dooya|窗帘/, "curtain"],
    [/light|yeelink|philips\.|zbmesh|giot\.|bulb|lamp|strip|灯带|筒灯|台灯/, "light"],
    [/plug|outlet|socket|valve|插排|插座|通断|水阀/, "outlet"],
    [/switch|ctrl_neutral|mesw|btsw|kg03hl|wall.?switch|开关/, "switch"],
    [/sensor|motion|magnet|smoke|gas|occupy|人体|门磁/, "sensor"],
    [/router|gateway|hub|wifi|repeater|miir\.|remote\.ir|网关|路由/, "hub"],
  ];

  function keysOf(d) {
    return ((d && d.controls) || []).map(function (c) { return c.key; });
  }

  function hasCurve(d) {
    var reads = Object.keys((d && d.readable) || {});
    for (var i = 0; i < reads.length; i++) {
      if (CURVE_KEYS.indexOf(reads[i]) >= 0) return true;
    }
    return false;
  }

  function categoryOf(d) {
    if (!d) return "generic";
    // 只看型号与产品名：设备名是用户自定义的（比如把开关叫「客厅灯」），
    // 拿它分类会把开关误判成灯
    var m = ((d.model || "") + " " + (d.product || "")).toLowerCase();
    for (var i = 0; i < MODEL_RULES.length; i++) {
      if (MODEL_RULES[i][0].test(m)) return MODEL_RULES[i][1];
    }

    // 型号认不出时才用能力兜底
    var keys = keysOf(d);
    var reads = Object.keys(d.readable || {});
    var sws = (d.switches || []).length;
    var tt = null;
    for (var j = 0; j < ((d && d.controls) || []).length; j++) {
      if (d.controls[j].key === "target-temperature") tt = d.controls[j];
    }
    if (keys.indexOf("brightness") >= 0 || keys.indexOf("color-temperature") >= 0) {
      return "light";
    }
    if (tt) return (tt.max && tt.max > 50) ? "appliance" : "climate";
    if (keys.indexOf("fan-level") >= 0) return "climate";
    if (!sws && (reads.indexOf("temperature") >= 0 ||
                 reads.indexOf("humidity") >= 0)) return "climate-sensor";
    if (reads.indexOf("power") >= 0 || reads.indexOf("voltage") >= 0 ||
        reads.indexOf("current") >= 0) return "outlet";
    if (sws >= 2) return "switch";
    return "generic";
  }

  /** 设备是否应在卡片/详情展示电源开关：类型以开关为主控，且确有开关属性。 */
  function toggleable(d) {
    if (!d) return false;
    if (!TOGGLE_CATS[categoryOf(d)]) return false;
    return ((d.switches || []).length > 0);
  }

  function sizeOf(d) {
    var c = categoryOf(d);
    var keys = keysOf(d);
    // 离线设备的控件整块不渲染（点了也不会成功），能摆的只剩
    // 图标 / 名称 / 「离线」/ 最后一次读数。这时候再占大卡就是一块空板子，
    // 空占一屏却什么也不给——按「有没有读数」收到小卡或中卡。
    if (d && d.online === false) {
      var hasRead = keys.length > 0
        || Object.keys((d && d.readable) || {}).length > 0;
      return hasRead ? "md" : "sm";
    }
    // 亮度 + 色温两个滑杆才给大卡；只有一个的灯中卡足够，避免空大卡
    if (c === "ir") {
      // 红外遥控：有命令或按键才给中卡（摆一排按钮），否则单格
      var blk = d && d.ir;
      var n = blk ? (((blk.cmds || []).length) || ((blk.keys || []).length)) : 0;
      return n > 0 ? "md" : "sm";
    }
    if (c === "light") {
      var lightCtrls = ["brightness", "color-temperature"].filter(function (k) {
        return keys.indexOf(k) >= 0;
      }).length;
      if (lightCtrls >= 2) return "lg";
      if (lightCtrls === 1) return "md";
    }
    // 大设备类别也按内容给尺寸：能力已解析且确实没曲线/控件时降到中卡；
    // 能力字段缺失（猜测态）保持大卡，避免把未知设备的内容裁掉
    if (LARGE.indexOf(c) >= 0) {
      var parsed = Array.isArray(d.controls) && d.readable !== undefined;
      if (parsed && !hasCurve(d) && keys.length < 2) return "md";
      return "lg";
    }
    if (hasCurve(d)) return "lg";
    if (MEDIUM.indexOf(c) >= 0) return "md";
    if (((d && d.switches) || []).length >= 2) return "md";
    if (keysOf(d).length >= 2) return "md";
    return "sm";
  }

  var API = {
    CATEGORY_LABELS: CATEGORY_LABELS,
    CURVE_KEYS: CURVE_KEYS,
    TOGGLE_CATS: TOGGLE_CATS,
    categoryOf: categoryOf,
    sizeOf: sizeOf,
    toggleable: toggleable,
    hasCurve: hasCurve,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.Cards = API;
})(typeof window !== "undefined" ? window : globalThis);
