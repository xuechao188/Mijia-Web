/* 家庭 / 房间两级分组与自定义分组的筛选逻辑。
 *
 * 纯函数、无 DOM 依赖：浏览器里挂到 window.Groups，Node 里可直接 require 测试。
 * 家庭与房间来自 /api/devices 的 home/room 字段（米家云端），
 * 自定义分组来自 /api/groups（本机持久化，可跨家庭组合设备）。
 */
(function (root) {
  "use strict";

  // 分组名里几乎不可能出现的分隔符，避免 "信地:客厅" 这类 key 冲突
  var SEP = "\u0001";

  function key(type, a, b) {
    if (type === "all") return "all";
    if (type === "unassigned") return "unassigned";
    return [type, a == null ? "" : String(a), b == null ? "" : String(b)].join(SEP);
  }

  function parseKey(k) {
    var p = String(k == null ? "all" : k).split(SEP);
    return { type: p[0] || "all", a: p[1] || "", b: p[2] || "" };
  }

  function byName(a, b) {
    return String(a.name || "").localeCompare(String(b.name || ""), "zh-CN");
  }

  function buildTree(devices) {
    var homeMap = {};
    var homeOrder = [];
    var unassigned = [];
    for (var i = 0; i < (devices || []).length; i++) {
      var d = devices[i] || {};
      var did = String(d.did);
      var home = String(d.home || "");
      var room = String(d.room || "");
      if (!home) { unassigned.push(did); continue; }
      if (!homeMap[home]) {
        homeMap[home] = {
          name: home, id: String(d.home_id || ""), dids: [],
          roomMap: {}, roomOrder: [],
        };
        homeOrder.push(home);
      }
      var h = homeMap[home];
      h.dids.push(did);
      if (!h.roomMap[room]) {
        h.roomMap[room] = {
          name: room, id: String(d.room_id || ""), dids: [],
        };
        h.roomOrder.push(room);
      }
      h.roomMap[room].dids.push(did);
    }
    var homes = homeOrder.map(function (name) {
      var h = homeMap[name];
      return {
        name: h.name, id: h.id, dids: h.dids,
        rooms: h.roomOrder.map(function (rn) {
          var r = h.roomMap[rn];
          return { name: r.name, id: r.id, dids: r.dids };
        }).sort(byName),
      };
    }).sort(byName);
    return { homes: homes, unassigned: unassigned };
  }

  function total(tree) {
    var t = tree || {};
    var n = (t.unassigned || []).length;
    for (var i = 0; i < (t.homes || []).length; i++) n += (t.homes[i].dids || []).length;
    return n;
  }

  function findHome(tree, name) {
    var hs = (tree || {}).homes || [];
    for (var i = 0; i < hs.length; i++) if (hs[i].name === name) return hs[i];
    return null;
  }

  function findRoom(tree, home, room) {
    var h = findHome(tree, home);
    if (!h) return null;
    for (var i = 0; i < (h.rooms || []).length; i++) {
      if ((h.rooms[i].name || "") === room) return h.rooms[i];
    }
    return null;
  }

  function findGroup(groups, id) {
    for (var i = 0; i < (groups || []).length; i++) {
      if (String(groups[i].id) === String(id)) return groups[i];
    }
    return null;
  }

  function nodes(tree, groups) {
    var out = [{ key: key("all"), type: "all", label: "全部设备",
                 count: total(tree) }];
    var hs = (tree || {}).homes || [];
    for (var i = 0; i < hs.length; i++) {
      var h = hs[i];
      out.push({ key: key("home", h.name), type: "home", label: h.name,
                 count: (h.dids || []).length });
      var rs = h.rooms || [];
      for (var j = 0; j < rs.length; j++) {
        var r = rs[j];
        out.push({ key: key("room", h.name, r.name), type: "room",
                   label: r.name || "未分房间", home: h.name,
                   count: (r.dids || []).length });
      }
    }
    if (((tree || {}).unassigned || []).length) {
      out.push({ key: key("unassigned"), type: "unassigned",
                 label: "未分配", count: tree.unassigned.length });
    }
    for (var k = 0; k < (groups || []).length; k++) {
      var g = groups[k];
      out.push({ key: key("group", g.id), type: "group", label: g.name,
                 id: String(g.id), count: (g.dids || []).length });
    }
    return out;
  }

  function matches(k, device, groups) {
    var f = parseKey(k);
    var d = device || {};
    if (f.type === "all") return true;
    if (f.type === "unassigned") return !String(d.home || "");
    if (f.type === "home") return String(d.home || "") === f.a;
    if (f.type === "room") {
      return String(d.home || "") === f.a && String(d.room || "") === f.b;
    }
    if (f.type === "group") {
      var g = findGroup(groups, f.a);
      return !!g && (g.dids || []).map(String).indexOf(String(d.did)) >= 0;
    }
    return true;
  }

  function count(k, tree, groups) {
    var f = parseKey(k);
    if (f.type === "all") return total(tree);
    if (f.type === "unassigned") return ((tree || {}).unassigned || []).length;
    if (f.type === "home") {
      var h = findHome(tree, f.a);
      return h ? (h.dids || []).length : 0;
    }
    if (f.type === "room") {
      var r = findRoom(tree, f.a, f.b);
      return r ? (r.dids || []).length : 0;
    }
    if (f.type === "group") {
      var g = findGroup(groups, f.a);
      return g ? (g.dids || []).length : 0;
    }
    return 0;
  }

  function label(k, tree, groups) {
    var f = parseKey(k);
    if (f.type === "all") return "全部设备";
    if (f.type === "unassigned") return "未分配";
    if (f.type === "home") return f.a;
    if (f.type === "room") return f.a + " / " + (f.b || "未分房间");
    if (f.type === "group") {
      var g = findGroup(groups, f.a);
      return g ? g.name : "自定义分组";
    }
    return "全部设备";
  }

  var API = {
    key: key, parseKey: parseKey, buildTree: buildTree, nodes: nodes,
    matches: matches, count: count, label: label, total: total,
  };

  if (typeof module !== "undefined" && module.exports) module.exports = API;
  else root.Groups = API;
})(typeof window !== "undefined" ? window : globalThis);
