/* 分组树 / 筛选纯函数回归：Node 直接跑，不依赖浏览器。 */
const G = require("../static/groups.js");

let n = 0;
function ok(cond, msg) {
  if (cond) { n++; console.log("  ✓", msg); }
  else { console.log("  ✗", msg); process.exit(1); }
}

const devices = [
  { did: "1", home: "信地", home_id: "h1", room: "卧室", room_id: "r1" },
  { did: "2", home: "信地", home_id: "h1", room: "厨房", room_id: "r2" },
  { did: "3", home: "西山银杏", home_id: "h2", room: "厨房", room_id: "r3" },
  { did: "4", home: "西山银杏", home_id: "h2", room: "客厅", room_id: "r4" },
  { did: "5", home: "西山银杏", home_id: "h2", room: "", room_id: "" },
  { did: "6", home: "", room: "" },
];
const groups = [{ id: "g1", name: "常用", dids: ["1", "4"] }];

// key 往返
ok(G.key("all") === "all", "全部设备 key 为 all");
ok(G.key("unassigned") === "unassigned", "未分配 key 为 unassigned");
const rk = G.key("room", "信地", "厨房");
ok(G.parseKey(rk).type === "room" && G.parseKey(rk).a === "信地"
   && G.parseKey(rk).b === "厨房", "两级 key 可还原家庭与房间");
ok(G.key("room", "a:b", "c") !== G.key("room", "a", "b:c"),
   "名字含冒号不会构造出冲突 key");
ok(G.parseKey(null).type === "all" && G.parseKey("").type === "all",
   "空 key 兜底为全部设备");

// 树结构
const tree = G.buildTree(devices);
ok(tree.homes.length === 2, "构造出 2 个家庭");
ok(tree.unassigned.length === 1 && tree.unassigned[0] === "6",
   "无家庭设备归入未分配");
const xd = tree.homes.find((h) => h.name === "信地");
const xs = tree.homes.find((h) => h.name === "西山银杏");
ok(xd.dids.length === 2 && xs.dids.length === 3, "家庭设备数按各自 did 统计");
ok(xd.rooms.some((r) => r.name === "厨房")
   && xs.rooms.some((r) => r.name === "厨房"),
   "两个家庭的同名房间各自保留，不被合并");
ok(xs.rooms.some((r) => r.name === "" && r.dids[0] === "5"),
   "有家庭无房间的设备不会丢失");
ok(G.total(tree) === 6, "总设备数不重不漏");

// 侧栏节点
const ns = G.nodes(tree, groups);
ok(ns[0].key === "all" && ns[0].count === 6, "首节点是全部设备且计数正确");
ok(ns.filter((x) => x.type === "room").length === 5, "生成 5 个房间节点");
ok(ns.filter((x) => x.type === "home").length === 2, "生成 2 个家庭节点");
ok(ns.some((x) => x.type === "unassigned" && x.count === 1),
   "未分配节点带设备数");
ok(ns.some((x) => x.type === "group" && x.label === "常用" && x.count === 2),
   "自定义分组节点带成员数");
const emptyRoom = ns.find((x) => x.type === "room" && x.label === "未分房间");
ok(!!emptyRoom && emptyRoom.count === 1, "空房间名显示为未分房间");

// 筛选
ok(devices.every((d) => G.matches("all", d, groups)), "全部设备匹配所有设备");
ok(G.matches(G.key("home", "信地"), devices[0], groups)
   && !G.matches(G.key("home", "信地"), devices[2], groups),
   "家庭筛选只命中本家庭设备");
ok(G.matches(G.key("room", "信地", "厨房"), devices[1], groups)
   && !G.matches(G.key("room", "信地", "厨房"), devices[2], groups),
   "两级房间筛选不误命中另一家庭的同名厨房");
ok(G.matches(G.key("room", "西山银杏", ""), devices[4], groups),
   "未分房间节点可筛出对应设备");
ok(G.matches("unassigned", devices[5], groups)
   && !G.matches("unassigned", devices[0], groups),
   "未分配筛选只命中无家庭设备");
ok(G.matches(G.key("group", "g1"), devices[0], groups)
   && !G.matches(G.key("group", "g1"), devices[2], groups),
   "自定义分组可跨家庭命中成员");
ok(!G.matches(G.key("group", "g404"), devices[0], groups),
   "已删除分组不再误命中");

// 计数与标题
ok(G.count(G.key("room", "信地", "厨房"), tree, groups) === 1,
   "房间计数按家庭隔离");
ok(G.count(G.key("group", "g1"), tree, groups) === 2, "分组计数正确");
ok(G.label(G.key("room", "信地", "厨房"), tree, groups) === "信地 / 厨房",
   "两级标题带家庭名");
ok(G.label(G.key("group", "g1"), tree, groups) === "常用", "分组标题正确");

console.log("groups_test: %d 项通过", n);
