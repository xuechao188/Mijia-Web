#!/usr/bin/env python3
"""Vue 设备网格（步骤④）不变量。

两类检查：
1) 运行时交叉校验：Node 22 --experimental-strip-types 直接加载 web/src/devices/*.ts，
   与旧界面 cards.js / device_icons.js / groups.js / card_types.js 的纯函数逐项比对，
   再加一组卡片模型（内容预算、离线降档、空壳收口）的行为断言。
2) 静态文本：组件接线、端点、样式钩子、旧前端零牵连。
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "web", "src")

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


PURE = [
    "devices/types.ts", "devices/cards.ts", "devices/icons.ts",
    "devices/groups.ts", "devices/readouts.ts", "devices/content.ts",
    "devices/labels.ts",
]

# ---- 1. 纯逻辑模块齐全 ----
for rel in PURE:
    ok(os.path.isfile(path(SRC, *rel.split("/"))), "新增 %s" % rel)

# ---- 2. 运行时交叉校验（Node 22 strip types） ----
with tempfile.TemporaryDirectory(prefix="vue_devices_") as tmp:
    for rel in PURE:
        text = read(path(SRC, *rel.split("/")))
        # Vite 用无扩展名导入，Node ESM 解不开；测试副本补 .ts 后缀
        text = re.sub(r"from '\./([A-Za-z]+)'", r"from './\1.ts'", text)
        open(path(tmp, rel.split("/")[-1]), "w", encoding="utf-8").write(text)

    probe = r'''
const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
const [ROOT, TMP] = process.argv.slice(2);
const J = (p) => require(ROOT + '/static/' + p);
const oldCards = J('cards.js');
const oldIcons = J('device_icons.js');
const oldGroups = J('groups.js');
const oldTypes = J('card_types.js');
const cards = await import('file://' + TMP + '/cards.ts');
const icons = await import('file://' + TMP + '/icons.ts');
const groups = await import('file://' + TMP + '/groups.ts');
const reads = await import('file://' + TMP + '/readouts.ts');
const content = await import('file://' + TMP + '/content.ts');
const labels = await import('file://' + TMP + '/labels.ts');

const checks = [];
const push = (name, v) => checks.push([name, !!v]);
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function dev(o) {
  return Object.assign({
    did: 'd1', name: '设备', model: '', product: '', home: '', room: '',
    online: true, controls: [], readable: {}, switches: [],
  }, o || {});
}
function ctrl(o) {
  return Object.assign({
    key: 'x', label: 'X', unit: '', kind: 'range', siid: 2, piid: 1,
    writable: true, readable: true, min: 0, max: 100, step: 1, svc: '',
  }, o || {});
}
const sw = (key, label) => ({ key, label, siid: 2, piid: 1 });

const samples = [
  dev({}),
  dev({ model: 'yeelink.light.lamp1', controls: [ctrl({ key: 'brightness' }), ctrl({ key: 'color-temperature' })] }),
  dev({ model: 'sensor_ht.v1', readable: { temperature: { unit: 'celsius' }, humidity: { unit: 'percentage' } } }),
  dev({ model: 'xiaomi.aircondition.mc1', switches: [sw('on', 'on')], controls: [ctrl({ key: 'target-temperature', max: 30 })] }),
  dev({ model: 'mijia.airfryer.st701', switches: [sw('on', 'on')], controls: [ctrl({ key: 'target-temperature', max: 200 })] }),
  dev({ model: 'zhimi.purifier.mb4', readable: { 'pm2.5-density': {} } }),
  dev({ model: 'rockrobo.vacuum.v1' }),
  dev({ model: 'chuangmi.camera.ipc009', actions: [] }),
  dev({ model: 'dooya.curtain.m1', switches: [sw('on', 'on')] }),
  dev({ model: 'chuangmi.plug.m3', readable: { power: { unit: 'watt' } }, switches: [sw('on', 'on')] }),
  dev({ model: 'ctrl_neutral.v1', switches: [sw('on1', 'left'), sw('on2', 'right'), sw('on3', 'middle')] }),
  dev({ model: 'sensor_magnet.v1' }),
  dev({ model: 'lumi.gateway.mgl03' }),
  dev({ product: '智能台灯', switches: [sw('on', 'on')] }),
  dev({ name: '客厅灯', model: 'switch.v1', switches: [sw('on', 'on')] }),
  dev({ model: 'unknown.thing', controls: [ctrl({ key: 'fan-level' })] }),
  dev({ model: 'unknown.thing', controls: [ctrl({ key: 'brightness' })] }),
  dev({ model: 'unknown.thing', readable: { power: {} } }),
  dev({ model: 'unknown.thing', switches: [sw('on1', 'on1'), sw('on2', 'on2')] }),
  dev({ model: 'yeelink.light.lamp1', online: false, controls: [ctrl({ key: 'brightness' })] }),
  dev({ model: 'sensor_ht.v1', online: false, readable: { temperature: {} } }),
  dev({ model: 'zhimi.purifier.mb4', online: false }),
  dev({ model: 'chuangmi.plug.m3', switches: [sw('on1', 'left'), sw('on2', 'right'), sw('on3', 'middle'), sw('on4', 'x'), sw('on5', 'y')] }),
  // 红外遥控：虚拟设备，控制面是命令/按键而不是开关（miir.* 必须落在 ir 类）
  dev({ did: 'ir.1', model: 'miir.tv.ir01',
        ir: { kind: 'tv', label: '电视遥控', cmds: [{ id: 'a:2:1', kind: 'action', group: '电源', label: '开机' }], keys: [{ id: 1, name: '电源' }] } }),
  dev({ did: 'ir.2', model: 'miir.remote.ir01', online: false,
        ir: { kind: 'remote', label: '自定义遥控', cmds: [], keys: [] } }),
];

// ---- cards.js ----
push('CATEGORY_LABELS 与旧版一致', eq(oldCards.CATEGORY_LABELS, cards.CATEGORY_LABELS));
push('CURVE_KEYS 与旧版一致', eq(oldCards.CURVE_KEYS, cards.CURVE_KEYS));
push('TOGGLE_CATS 与旧版一致', eq(oldCards.TOGGLE_CATS, cards.TOGGLE_CATS));
for (const d of samples) {
  const tag = (d.model || d.product || 'generic') + '/' + d.online;
  push('categoryOf ' + tag + ' 与旧版一致', oldCards.categoryOf(d) === cards.categoryOf(d));
  push('sizeOf ' + tag + ' 与旧版一致', oldCards.sizeOf(d) === cards.sizeOf(d));
  push('toggleable ' + tag + ' 与旧版一致', oldCards.toggleable(d) === cards.toggleable(d));
  push('hasCurve ' + tag + ' 与旧版一致', oldCards.hasCurve(d) === cards.hasCurve(d));
}
push('14 类分类齐全', eq([...new Set(samples.map((d) => cards.categoryOf(d)))].sort(),
  ['appliance','camera','cleaner','climate','climate-sensor','curtain','generic','hub','ir','light','outlet','purifier','sensor','switch'].sort()));

// ---- device_icons.js ----
push('CATS 14 类与旧版一致', eq(oldIcons.CATS, icons.CATS));
push('PATHS 与旧版逐字一致', eq(oldIcons.PATHS, icons.PATHS));
for (const c of oldIcons.CATS) {
  push('svg(' + c + ') 与旧版逐字一致', oldIcons.svg(c) === icons.svg(c));
  push('has(' + c + ') 与旧版一致', oldIcons.has(c) === icons.has(c));
}
push('未知类别回退 generic', icons.svg('nope') === oldIcons.svg('generic'));
push('svg 根写死 fill="none"', icons.svg('light').includes('fill="none"'));
push('svg 不写死颜色', !/stroke="#/.test(icons.svg('light')));

// ---- groups.js ----
const treeDevices = [
  dev({ did: '1', home: '信地', home_id: 'h1', room: '客厅', room_id: 'r1' }),
  dev({ did: '2', home: '信地', home_id: 'h1', room: '卧室', room_id: 'r2' }),
  dev({ did: '3', home: '信地', home_id: 'h1', room: '客厅', room_id: 'r1' }),
  dev({ did: '4', home: '老家', home_id: 'h2', room: '客厅', room_id: 'r3' }),
  dev({ did: '5' }),
];
const gl = [{ id: 'g1', name: '夜间', dids: ['1', '4'] }, { id: 'g2', name: '常在', dids: ['3'] }];
const tree = groups.buildTree(treeDevices);
push('buildTree 与旧版一致', eq(oldGroups.buildTree(treeDevices), tree));
push('total 与旧版一致', oldGroups.total(tree) === groups.total(tree));
const nav = groups.nodes(tree, gl);
push('nodes 与旧版一致', eq(oldGroups.nodes(tree, gl), nav));
for (const n of nav) {
  push('label(' + n.type + ') 与旧版一致', oldGroups.label(n.key, tree, gl) === groups.label(n.key, tree, gl));
  push('count(' + n.type + ') 与旧版一致', oldGroups.count(n.key, tree, gl) === groups.count(n.key, tree, gl));
  for (const d of treeDevices) {
    push('matches(' + n.type + ',' + d.did + ') 与旧版一致',
      oldGroups.matches(n.key, d, gl) === groups.matches(n.key, d, gl));
  }
  push('parseKey(' + n.type + ') 与旧版一致', eq(oldGroups.parseKey(n.key), groups.parseKey(n.key)));
}
for (const spec of [['all'], ['unassigned'], ['home', '信地'], ['room', '信地', '客厅'], ['group', 'g1']]) {
  const k = oldGroups.key(...spec);
  push('key(' + spec.join(',') + ') 与旧版一致', k === groups.key(...spec));
}

// ---- roomNodes：家庭在顶部选，列表只留该家庭的房间 ----
const rn = groups.roomNodes(tree, '信地');
push('roomNodes 首项是该家庭全部设备',
  rn[0].type === 'home' && rn[0].label === '全部设备' && rn[0].count === 3);
push('roomNodes 只列本家庭房间',
  rn.filter((n) => n.type === 'room').map((n) => n.label).join() === '客厅,卧室');
push('roomNodes 不混入其它家庭',
  rn.every((n) => (n.home || '') !== '老家'));
push('roomNodes 不再追加未分配', rn.every((n) => n.type !== 'unassigned'));
push('roomNodes 未知家庭返回空列表', groups.roomNodes(tree, '不存在').length === 0);
push('roomNodes 键可直接用于筛选',
  rn[1].key === groups.key('room', '信地', '客厅')
  && groups.matches(rn[1].key, dev({ home: '信地', room: '客厅' }), gl)
  && !groups.matches(rn[1].key, dev({ home: '信地', room: '卧室' }), gl));
push('roomNodes 与侧栏旧 nodes 数量对齐',
  rn.filter((n) => n.type === 'room').length
  === groups.nodes(tree, []).filter((n) => n.type === 'room' && n.home === '信地').length);

// ---- card_types.js 纯函数 ----
push('READOUTS 与旧版一致', eq(oldTypes.READOUTS, reads.READOUTS));
push('UNIT_MAP 覆盖 8 种 spec 单位', Object.keys(reads.UNIT_MAP).length === 8 && reads.UNIT_MAP.celsius === '°C');
const products = ['', 'Temperature and Humidity Sensor', '米家智能插座', 'lumi.sensor_ht.v1',
  'Xiaomi Air Fryer', '智能门锁', 'xyz.unknown', 'zhimi.airpurifier.mb4'];
for (const p of products) {
  push('productLabel("' + p + '") 与旧版一致',
    oldTypes.productLabel({ product: p }) === reads.productLabel({ product: p }));
}
for (const k of Object.keys(oldTypes.READOUTS).concat(['brightness', 'weird_key'])) {
  push('labelOf(' + k + ') 与旧版一致', oldTypes.labelOf(k, samples[1]) === reads.labelOf(k, samples[1]));
  for (const v of [0, 1, 24.36, true, false, null, 'auto']) {
    push('formatValue(' + k + ',' + String(v) + ') 与旧版一致',
      oldTypes.formatValue(k, v, samples[1]) === reads.formatValue(k, v, samples[1]));
  }
}
const switchSamples = [sw('on', 'left'), sw('on2', 'right'), sw('on1', 'on1'), sw('x', 'Switch Service'), sw('y', '')];
switchSamples.forEach((s, i) => {
  push('switchLabel(' + i + ') 与旧版一致',
    oldTypes.switchLabel(s, i) === reads.switchLabel(s, i));
});
const enumDev = dev({ model: 'xiaomi.aircondition.mc1', controls: [
  ctrl({ key: 'mode', kind: 'enum', options: [{ v: 0, t: '制冷' }, { v: 1, t: '制热' }] }),
  ctrl({ key: 'night-vision', kind: 'bool', svc: 'camera-control' }),
] });
const liveCases = [
  {}, { on: true }, { temperature: 24.36, humidity: 51, power: 12.4, mode: 1 },
  { 'night-vision': false, motion: true, contact: false, 'pm2.5-density': 8 },
];
for (const d of samples.concat([enumDev])) {
  for (const live of liveCases) {
    push('readoutEntries(' + (d.model || 'generic') + ') 与旧版一致',
      eq(oldTypes.readoutEntries(d, live), reads.readoutEntries(d, live)));
  }
  for (const size of ['sm', 'md', 'lg']) {
    for (const cat of oldIcons.CATS) {
      push('cardControls(' + cat + ',' + size + ') 与旧版一致',
        eq(oldTypes.cardControls(d, cat, size), reads.cardControls(d, cat, size)));
    }
  }
}
const series = { temperature: [[1, 21], [2, 22.5], [3, 20]], humidity: [[1, 50]],
  'unknown-key': [[1, 1], [2, 2]] };
for (const d of samples) {
  push('curveEntries(' + (d.model || 'generic') + ') 与旧版一致',
    eq(oldTypes.curveEntries(d, series), reads.curveEntries(d, series)));
}
for (const pts of [[], [[1, 1]], [[1, 1], [2, 5], [3, 2]], [[1, 3], [2, 3], [3, 3]], [[1, NaN], [2, 4]]]) {
  for (const opt of [{}, { w: 320, h: 68 }, { w: 240, h: 48, color: '#f00' }]) {
    const norm = (s) => s.replace(/g[a-z0-9]{6}/g, 'gXXXXXX');
    push('sparkline(' + pts.length + '点) 与旧版一致',
      norm(oldTypes.sparkline(pts, opt)) === norm(reads.sparkline(pts, opt)));
  }
}

// ---- content.ts：状态 / 上下文 / 排序 / 内容预算 ----
const statusCases = [
  [dev({ online: false }), { multi: false, sws: [], isOn: false, offline: true, live: {} }, '离线'],
  [dev({ model: 'ctrl_neutral.v1', switches: [sw('on1', ''), sw('on2', ''), sw('on3', '')] }),
    { multi: true, sws: [sw('on1', ''), sw('on2', ''), sw('on3', '')], isOn: true, offline: false,
      live: { on1: true, on2: true, on3: false } }, '2/3 路开'],
  [dev({ model: 'lumi.gateway.mgl03' }), { multi: false, sws: [], isOn: false, offline: false, live: {} }, ''],
  [dev({ model: 'yeelink.light.lamp1', switches: [sw('on', '')] }),
    { multi: false, sws: [sw('on', '')], isOn: true, offline: false, live: { on: true } }, '已开启'],
  [dev({ model: 'yeelink.light.lamp1', switches: [sw('on', '')] }),
    { multi: false, sws: [sw('on', '')], isOn: false, offline: false, live: { on: false } }, '已关闭'],
];
for (const [d, o, want] of statusCases) {
  push('cardStatus -> ' + (want || '空'), content.cardStatus(d, o) === want);
}
push('cardContext 单家庭只写房间',
  content.cardContext(dev({ home: '信地', room: '客厅' }), 1) === '客厅');
push('cardContext 多家庭带家庭名',
  content.cardContext(dev({ home: '信地', room: '客厅' }), 2) === '信地 · 客厅');
push('cardContext 无房间用产品名',
  content.cardContext(dev({ product: '米家智能插座' }), 1) === '智能插座');

const ordered = [dev({ did: 'a' }), dev({ did: 'b' }), dev({ did: 'c' }), dev({ did: 'd' })];
push('applyOrder 按 order 排前', eq(content.applyOrder(ordered, ['c', 'a']).map((d) => d.did), ['c', 'a', 'b', 'd']));
push('applyOrder 空 order 保持原序', eq(content.applyOrder(ordered, []).map((d) => d.did), ['a', 'b', 'c', 'd']));
push('applyOrder 不改原数组', ordered.map((d) => d.did).join() === 'a,b,c,d');
push('cardSize 覆盖优先自动',
  content.cardSize(dev({ did: 'a', model: 'yeelink.light.lamp1' }), { a: 'sm' }) === 'sm');
push('cardSize 无覆盖走自动',
  content.cardSize(dev({ did: 'a', model: 'yeelink.light.lamp1' }), {}) === oldCards.sizeOf(dev({ did: 'a', model: 'yeelink.light.lamp1' })));
const vlist = [dev({ did: '1', name: '台灯' }), dev({ did: '2', home: '信地', room: '客厅' })];
push('visibleDevices 搜索命中自定义名',
  eq(content.visibleDevices(vlist, 'all', [], '床头', { sizes: {}, order: [] }, { 1: '床头灯' }).map((d) => d.did), ['1']));
push('visibleDevices 搜索命中云端名',
  eq(content.visibleDevices(vlist, 'all', [], '客厅', { sizes: {}, order: [] }, {}).map((d) => d.did), ['2']));
push('visibleDevices 分组过滤',
  eq(content.visibleDevices(vlist, groups.key('group', 'g1'), [{ id: 'g1', name: 'x', dids: ['1'] }], '', { sizes: {}, order: [] }, {}).map((d) => d.did), ['1']));

// ---- 离线沉底：可用设备先进首屏 ----
const mix = [dev({ did: 'a', online: false }), dev({ did: 'b' }), dev({ did: 'c', online: false }), dev({ did: 'd' })];
push('onlineFirst 在线优先、离线沉底',
  eq(content.onlineFirst(mix).map((d) => d.did), ['b', 'd', 'a', 'c']));
push('onlineFirst 组内保持原序',
  eq(content.onlineFirst([dev({ did: 'x' }), dev({ did: 'y' }), dev({ did: 'z' })]).map((d) => d.did), ['x', 'y', 'z']));
push('onlineFirst 不改原数组', mix.map((d) => d.did).join() === 'a,b,c,d');
push('visibleDevices 排序在前也压不住离线沉底',
  eq(content.visibleDevices(
    [dev({ did: '1', online: false }), dev({ did: '2' }), dev({ did: '3' })],
    'all', [], '', { sizes: {}, order: ['1', '2', '3'] }, {}).map((d) => d.did), ['2', '3', '1']));
push('visibleDevices 家庭筛选后同样离线沉底',
  eq(content.visibleDevices(
    [dev({ did: '1', home: '信地', online: false }), dev({ did: '2', home: '信地' }),
     dev({ did: '3', home: '临时' })],
    groups.key('home', '信地'), [], '', { sizes: {}, order: [] }, {}).map((d) => d.did), ['2', '1']));
push('statCounts 多键任一路开即算',
  eq(content.statCounts([dev({ did: '1', switches: [sw('on1', ''), sw('on2', '')] }), dev({ did: '2' })],
    { 1: { on1: false, on2: true }, 2: { on: false } }), { total: 2, online: 2, on: 1 }));

// ---- 统计条类型分组：把十几个细类收成用户嘴里的四类 ----
const groupDevs = [
  dev({ did: 'g1', model: 'yeelink.light.lamp1' }),          // 照明（灯具）
  dev({ did: 'g2', model: 'ctrl_neutral.v1' }),               // 照明（墙面开关）
  dev({ did: 'g3', model: 'miaomiaoce.sensor_ht.t2' }),        // 环境（温湿度）
  dev({ did: 'g4', model: 'zhimi.airpurifier.mb3' }),          // 环境（净化）
  dev({ did: 'g5', model: 'lumi.sensor_motion.aq2' }),         // 传感器
  dev({ did: 'g6', model: 'qmi.plug.2' }),                     // 其它（插座）
];
const gs = content.statGroups(groupDevs, { g1: { on: true }, g2: { on: false }, g6: { on: true } });
push('statGroups 顺序固定 照明→环境→传感器→其它',
  eq(gs.map((g) => g.key), ['light', 'env', 'sensor', 'other']));
push('statGroups 照明含开关与灯具', gs[0].count === 2 && gs[0].label === '照明');
push('statGroups 环境含温湿度与净化', gs[1].count === 2 && gs[1].label === '环境');
push('statGroups 传感器只放纯探测器', gs[2].count === 1);
push('statGroups 插座归其它', gs[3].count === 1);
push('statGroups 开着台数按组统计', gs[0].on === 1 && gs[3].on === 1 && gs[1].on === 0);
push('statGroups 空组不占位',
  eq(content.statGroups([dev({ did: 'p' })], {}).map((g) => g.key), ['other']));
push('statGroups 空范围返回空表（不硬塞一排 0）', content.statGroups([], {}).length === 0);

// ---- 统计条点击筛选：第二维，叠加在家庭/房间之上 ----
push('filterByStat 空串原样返回（不复制数组）',
  content.filterByStat(groupDevs, '') === groupDevs);
push('filterByStat 照明 = 灯具 + 开关',
  eq(content.filterByStat(groupDevs, 'light').map((d) => d.did), ['g1', 'g2']));
push('filterByStat 环境 = 温湿度 + 净化',
  eq(content.filterByStat(groupDevs, 'env').map((d) => d.did), ['g3', 'g4']));
push('filterByStat online 只看在线',
  eq(content.filterByStat([dev({ did: 'a' }), dev({ did: 'b', online: false })], 'online')
    .map((d) => d.did), ['a']));
push('filterByStat 不认识的 key 不误伤（返回空而不是全量）',
  content.filterByStat(groupDevs, 'nope').length === 0);

const baseOpt = (o) => Object.assign({ live: {}, history: {}, names: {}, metrics: [], sizes: {}, homesCount: 1 }, o || {});
const offLight = dev({ did: 'x', model: 'yeelink.light.lamp1', online: false,
  controls: [ctrl({ key: 'brightness' })], switches: [sw('on', '')], readable: { power: {} } });
const offCard = content.buildCard(offLight, baseOpt({ live: { on: true, power: 12 } }));
push('buildCard 离线不渲染开关', offCard.switches.length === 0 && offCard.chips.length === 0);
push('buildCard 离线不渲染滑杆', offCard.ctrls.length === 0);
push('buildCard 离线不画曲线', offCard.curves.length === 0);
push('buildCard 离线状态只说离线', offCard.subText === '离线' && offCard.subIsStatus);
push('buildCard 离线保留最后读数', offCard.reads.some((r) => r.key === 'power'));

const bare = dev({ did: 'y', model: 'zhimi.purifier.mb4', readable: { 'pm2.5-density': {} } });
const bareCard = content.buildCard(bare, baseOpt());
push('buildCard 只有图标/名称时收口', bareCard.bare === true);
push('buildCard 收口时不铺档案', bareCard.detailRows.length === 4); // 由组件按 bare 决定不渲染

const mdLamp = dev({ did: 'z', model: 'yeelink.light.lamp1',
  controls: [ctrl({ key: 'brightness' }), ctrl({ key: 'color-temperature' })],
  readable: { temperature: {} }, switches: [sw('on', '')] });
const mdCard = content.buildCard(mdLamp, baseOpt({ sizes: { z: 'md' }, live: { temperature: 24, brightness: 60 } }));
push('buildCard 中卡有滑杆就不叠读数', mdCard.reads.length === 0 && mdCard.ctrls.length === 1);
push('buildCard 中卡有滑杆不铺 chip', mdCard.chips.length === 0);

const multiDev = dev({ did: 'm', model: 'ctrl_neutral.v1',
  switches: [sw('on1', 'left'), sw('on2', 'right'), sw('on3', 'middle')],
  readable: { temperature: {} }, controls: [ctrl({ key: 'mode', kind: 'enum', options: [{ v: 0, t: 'A' }] })] });
const multiCard = content.buildCard(multiDev, baseOpt({ sizes: { m: 'lg' }, live: { temperature: 24, on1: true } }));
push('buildCard 多键只铺前 4 路', multiCard.switches.length === 3 && multiCard.switchMore === 0);
push('buildCard 多键不叠读数与 chip', multiCard.reads.length === 0 && multiCard.chips.length === 0);
const fiveCard = content.buildCard(dev({ did: 'm5', model: 'ctrl_neutral.v1',
  switches: [sw('on1', ''), sw('on2', ''), sw('on3', ''), sw('on4', ''), sw('on5', '')] }), baseOpt());
push('buildCard 超过 4 路提示去抽屉', fiveCard.switches.length === 4 && fiveCard.switchMore === 1);

const smDev = dev({ did: 's', model: 'sensor_magnet.v1', readable: { temperature: {} } });
const smCard = content.buildCard(smDev, baseOpt({ sizes: { s: 'sm' }, live: { temperature: 24.3 } }));
push('buildCard 小卡把有单位读数并进副标题', smCard.subText.includes('24.3'));
push('buildCard 小卡不铺读数区', smCard.reads.length === 0);
const smBare = content.buildCard(dev({ did: 's2', model: 'sensor_magnet.v1', readable: { mode: {} } }),
  baseOpt({ live: { mode: 0 } }));
push('buildCard 小卡拒绝无标签裸数字', !smBare.subText.includes(' · 0') && !smBare.subText.includes('0'));

const lgCurve = dev({ did: 'c', model: 'sensor_ht.v1', readable: { temperature: {} } });
const lgCard = content.buildCard(lgCurve, baseOpt({
  live: { temperature: 24 }, history: { temperature: [[1, 21], [2, 22], [3, 24]] },
}));
push('buildCard 大卡画一条曲线', lgCard.curves.length === 1 && lgCard.curves[0].key === 'temperature');
push('buildCard 大卡有分类内容不收口', lgCard.bare === false);

// ---- 英文枚举 / 动作名必须译成中文（只改展示，不动云端值） ----
const zhHas = (s) => /[\u4e00-\u9fff]/.test(String(s));
push('optionLabel 风速档位', labels.optionLabel('fan-level', 'Low') === '低档'
  && labels.optionLabel('fan-level', 'Medium') === '中档'
  && labels.optionLabel('fan-level', 'High') === '高档'
  && labels.optionLabel('fan-level', 'Auto') === '自动'
  && labels.optionLabel('fan-level', 'Stir-fry') === '爆炒');
push('optionLabel 空调模式', labels.optionLabel('mode', 'Cool') === '制冷'
  && labels.optionLabel('mode', 'Heat') === '制热'
  && labels.optionLabel('mode', 'Dry') === '除湿'
  && labels.optionLabel('mode', 'Ventilate') === '通风');
push('optionLabel 灯光模式', labels.optionLabel('mode', 'Night Light') === '夜灯'
  && labels.optionLabel('mode', 'Reading') === '阅读'
  && labels.optionLabel('mode', 'Eye Protection') === '护眼'
  && labels.optionLabel('mode', 'Dusk') === '傍晚');
push('optionLabel 洗衣机模式', labels.optionLabel('mode', 'Quick Wash') === '快洗'
  && labels.optionLabel('mode', 'Down Coat') === '羽绒服'
  && labels.optionLabel('mode', 'Drum Clean') === '筒清洁');
push('optionLabel 厨电前缀保留烹饪方式',
  labels.optionLabel('mode', 'AF-CHICKEN-WINGS') === '炸·鸡翅'
  && labels.optionLabel('mode', 'STM-EGG') === '蒸·鸡蛋'
  && labels.optionLabel('mode', 'SS-BIRDS-NEST') === '炖·燕窝'
  && labels.optionLabel('mode', 'SF-DUMPLINGS') === '煎·饺子'
  && labels.optionLabel('mode', 'BK-PIZZA') === '烘焙·披萨'
  && labels.optionLabel('mode', 'VD-SALMON') === '慢煮·三文鱼');
push('optionLabel 只有烹饪方式的前缀项',
  labels.optionLabel('mode', 'RH-AIR-FRY') === '空气炸'
  && labels.optionLabel('mode', 'RS-ROASTING') === '烘烤'
  && labels.optionLabel('mode', 'FM-FERMENTATION') === '发酵'
  && labels.optionLabel('mode', 'AD-AIR-DRIED') === '风干'
  && labels.optionLabel('mode', 'TD-THAWED') === '解冻');
push('optionLabel 驼峰模式名', labels.optionLabel('mode', 'AgeMode') === '年龄模式'
  && labels.optionLabel('mode', 'SoftMode') === '柔和模式'
  && labels.optionLabel('mode', 'CleanMode') === '清洁模式');
push('optionLabel 空值类选项', labels.optionLabel('mode', 'None') === '无'
  && labels.optionLabel('mode', 'NULL') === '无'
  && labels.optionLabel('mode', 'OFF') === '关'
  && labels.optionLabel('mode', 'ON') === '开');
push('optionLabel 自定义场景序号',
  labels.optionLabel('mode', 'My Mode-Scenario 3') === '自定义场景 3');
push('optionLabel 温度档带单位', labels.optionLabel('target-temperature', '60') === '60℃'
  && labels.optionLabel('target-temperature', 'Cold Water') === '冷水');
push('optionLabel 中文原样返回、空值不抛错',
  labels.optionLabel('mode', '制冷') === '制冷'
  && labels.optionLabel('mode', '') === '' && labels.optionLabel('mode', null) === '');
// 前缀 × 食材的任一组合都必须可译，漏词会在这里露出来
const PFX = ['AF', 'BK', 'SS', 'STM', 'SF', 'VD'];
const ITEM = ['BEEF-STEAK', 'CHICKEN-WINGS', 'FROZEN-FRIES', 'PORK-BELLY', 'SHRIMP',
  'SWEET-POTATO', 'EGG', 'EGG-CUSTARD', 'FISH', 'MEAT', 'SEAFOOD', 'CORN', 'BUN',
  'BREAD', 'CAKE', 'CHEESE-TART', 'PIZZA', 'DUMPLINGS', 'VEGETABLES', 'SALMON',
  'STEW', 'DESSERT', 'BABY-PORRIDGE', 'BIRDS-NEST', 'MISCELLANEOUS-GRAINS', 'CUSTOM'];
const pfxBad = [];
for (const P of PFX) for (const I of ITEM) {
  if (!zhHas(labels.optionLabel('mode', P + '-' + I))) pfxBad.push(P + '-' + I);
}
push('厨电前缀组合全部可译（' + PFX.length * ITEM.length + ' 组）', pfxBad.length === 0);
push('actionLabel 查表项', labels.actionLabel('start-room-sweep') === '清扫指定房间'
  && labels.actionLabel('find-device') === '查找设备'
  && labels.actionLabel('start-p2p-stream') === '开始取流');
push('actionLabel 词根规则', labels.actionLabel('brightness-up') === '亮度 ＋'
  && labels.actionLabel('brightness-down') === '亮度 －'
  && labels.actionLabel('fan-speed-up') === '风速 ＋'
  && labels.actionLabel('cct-down') === '色温 －'
  && labels.actionLabel('temperature-switch') === '温度 开关');
push('actionLabel 模式型动作名', labels.actionLabel('normal-mode') === '标准模式'
  && labels.actionLabel('wireless-mode') === '无线模式'
  && labels.actionLabel('jog-mode') === '点动模式'
  && labels.actionLabel('mixed-mode') === '混合模式');
push('actionLabel 中文原样返回、空值不抛错', labels.actionLabel('开始清扫') === '开始清扫'
  && labels.actionLabel('') === '' && labels.actionLabel(undefined) === '');

// ---- 家庭 → 房间两级导航（少了 home 节点就只剩一串房间） ----
const treeS = groups.buildTree([
  dev({ did: 'n1', home: '信地', room: '客厅' }),
  dev({ did: 'n2', home: '信地', room: '厨房' }),
  dev({ did: 'n3', home: '西山银杏', room: '客厅' }),
]);
const nodesS = groups.nodes(treeS, []);
push('两个家庭各产出 home 节点', nodesS.filter((n) => n.type === 'home').length === 2);
push('home 节点排在自家房间之前',
  nodesS.findIndex((n) => n.type === 'home' && n.label === '信地')
    < nodesS.findIndex((n) => n.type === 'room' && n.home === '信地'));
push('房间节点带 home 归属（重名客厅可分）',
  nodesS.filter((n) => n.type === 'room' && n.label === '客厅').length === 2
  && nodesS.filter((n) => n.type === 'room' && n.home === '信地').length === 2);

const fail = checks.filter(([, v]) => !v);
console.log(JSON.stringify({ total: checks.length, fail: fail.map(([n]) => n) }));
if (fail.length) { console.error('FAILED:\n' + fail.map(([n]) => n).join('\n')); process.exit(1); }
'''
    probe_path = path(tmp, "probe.mjs")
    open(probe_path, "w", encoding="utf-8").write(probe)
    proc = subprocess.run(
        ["node", "--experimental-strip-types", probe_path, ROOT, tmp],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        print(proc.stdout[-4000:])
        print(proc.stderr[-4000:])
        sys.exit(1)
    payload = {}
    for line in proc.stdout.strip().splitlines():
        if line.startswith("{"):
            import json
            payload = json.loads(line)
    ok(payload.get("fail") == [], "Node 运行时交叉校验 %s 项全过" % payload.get("total", 0))
    for _ in range(int(payload.get("total", 0))):
        ok_n[0] += 1  # 计数与③一致：每个探针断言都计入

# ---- 3. 旧前端零牵连 ----
app_py = read(path(ROOT, "app.py"))
config_py = read(path(ROOT, "config.py"))
ok("UI_FLAVOR" in config_py and "UI_FLAVOR" in app_py, "后端入口仍由 UI_FLAVOR 控制")
ok('send_from_directory(STATIC_DIR, "index.html")' in app_py, "旧入口仍可一键回退")

# ---- 4. 组件与外壳接线 ----
COMPONENTS = [
    "App.vue", "components/Sidebar.vue", "components/HomeSwitcher.vue",
    "components/DeviceGrid.vue", "components/DeviceCard.vue",
    "components/DeviceDrawer.vue",
]
for rel in COMPONENTS:
    ok(os.path.isfile(path(SRC, *rel.split("/"))), "新增/改造 %s" % rel)

app_vue = read(path(SRC, "App.vue"))
for name in ["LoginPage", "Sidebar", "DeviceGrid", "DeviceDrawer",
             "useThemeStore", "useAuthStore", "useDevicesStore"]:
    ok(name in app_vue, "App.vue 接入 %s" % name)
ok("auth.phase !== 'app'" in app_vue, "未登录时登录页仍是唯一内容")
ok("store.bootstrap()" in app_vue and "store.startPolling()" in app_vue,
   "进入 app 态才拉取设备并起轮询")
ok("store.stopPolling()" in app_vue, "退出登录/卸载时停轮询")
ok('class="stage"' in app_vue and 'class="topbar m-glass m-glass-rail"' in app_vue,
   "顶栏走浮层玻璃材质")

# 家庭在左上角品牌右侧切换，房间只留在侧栏列表里（米家式层级）
ok("<RoomSwitcher" not in app_vue, "顶栏不再重复挂房间切换器")
side_vue = read(path(SRC, "components", "Sidebar.vue"))
ok("<HomeSwitcher" in side_vue, "Sidebar 在品牌行右侧挂家庭切换器")
ok(side_vue.index("<HomeSwitcher") < side_vue.index('class="rail-search"'),
   "家庭切换器在品牌行内、搜索框之上")
hs_vue = read(path(SRC, "components", "HomeSwitcher.vue"))
for needle in ["store.activeHome", "store.homes", "store.setHome(",
               'role="listbox"', 'aria-haspopup="listbox"', ":aria-selected",
               "Escape", "removeEventListener('pointerdown'"]:
    ok(needle in hs_vue, "HomeSwitcher 接线 %s" % needle)
ok("store.roomNav" in side_vue, "侧栏列表只渲染当前家庭的房间")
ok("store.navNodes" not in side_vue, "侧栏不再渲染家庭与房间两级树")
ok("'nav-' + n.type" in side_vue,
   "首项「全部设备」与房间行仍用两级样式区分")
ok(">房间<" in side_vue, "侧栏房间列表有「房间」小标题")
ok("store.roomNav.length" in side_vue, "房间列表为空时给出提示")
# 侧栏只管导航：主题、刷新、退出统一收在顶栏右端，不再重复一份
ok("rail-foot" not in side_vue, "侧栏不再有底部动作区")
for gone in ["退出登录", "刷新设备", "<ThemePanel", "store.stats.total"]:
    ok(gone not in side_vue, "侧栏不再重复 %s" % gone)

# 顶栏右端动作组：主题 / 刷新设备 / 退出登录 + 外观浮层
for needle in [">主题<", ">刷新设备<", ">退出登录<", "<ThemePanel", "ref=\"actionsEl\"",
               "store.refresh()", "auth.logout()"]:
    ok(needle in app_vue, "顶栏动作组 %s" % needle)
ok('class="top-actions"' in app_vue, "三个动作收在同一个定位容器里")
# 点面板外面要收起：capture 阶段监听 pointerdown，不用冒泡依赖面板内部
ok("addEventListener('pointerdown', onDocPointerDown, true)" in app_vue,
   "外观浮层在外部 pointerdown 时收起")
ok("removeEventListener('pointerdown', onDocPointerDown, true)" in app_vue,
   "卸载时解绑外部点击监听")
ok("actionsEl.value" in app_vue and ".contains(e.target" in app_vue,
   "用锚点容器判断点击是否落在浮层内")
ok("e.key === 'Escape'" in app_vue, "Esc 也能收起外观浮层")
ok("store.mainTab, () => { themeOpen.value = false }" in app_vue,
   "切换主标签页时收起外观浮层")
ok("if (did) themeOpen.value = false" in app_vue, "打开设备抽屉时收起外观浮层")
ok('class="steps' not in app_vue, "页面底部不再挂迁移进度条")

theme_vue = read(path(SRC, "components", "ThemePanel.vue"))
ok("tp-state" not in theme_vue, "外观面板不再输出 data-* 调参明细")
for gone in ["data-theme=", "data-preset=", "data-density="]:
    ok(gone not in theme_vue, "外观面板不再显示 %s" % gone)

grid_vue = read(path(SRC, "components", "DeviceGrid.vue"))
for needle in ["buildCard(", "store.visible", "store.layout.sizes",
               "@open=\"store.openDrawer\"", "onDragStart", "store.saveOrder("]:
    ok(needle in grid_vue, "DeviceGrid 接线 %s" % needle)

card_vue = read(path(SRC, "components", "DeviceCard.vue"))
for needle in ["v-html=\"icon\"", "model.offline", "model.bare",
               "mini-switch in-head", "ct-readouts", "ct-controls", "ct-chart-svg"]:
    ok(needle in card_vue, "DeviceCard 保留 %s" % needle)

drawer_vue = read(path(SRC, "components", "DeviceDrawer.vue"))
for needle in ["Escape", "store.closeDrawer()", "store.setName(", "store.setSize(",
               "store.toggleMetric(", "store.setControl(", "store.postGroups(",
               "store.setDrawerHours(", "dr-range", "dr-history-head"]:
    ok(needle in drawer_vue, "DeviceDrawer 接线 %s" % needle)
# 枚举按钮必须走中文映射，不能再把云端英文原样铺出来
ok("optionLabel(c.key, o.t)" in drawer_vue, "DeviceDrawer 枚举选项走中文映射")
ok("{{ o.t }}" not in drawer_vue, "DeviceDrawer 不再直出云端英文选项")

cam_vue = read(path(SRC, "components", "CameraPanel.vue"))
ok("actionLabel(a.name)" in cam_vue, "CameraPanel 动作名走中文映射")
ok("{{ a.name }}" not in cam_vue, "CameraPanel 不再直出英文动作名")

ok("productLabel(d.value)" in drawer_vue, "抽屉产品名走中文映射")
ok("d.value.product ||" not in drawer_vue, "抽屉不再直出云端英文产品名")
ok("CATEGORY_LABELS[cat.value]" in drawer_vue, "认不出的产品名退回类别名")

reads_ts = read(path(SRC, "devices", "readouts.ts"))
ok("return optionLabel(key, o.t)" in reads_ts, "readoutText 用中文选项名")
ok("return String(o.t)" not in reads_ts, "readoutText 不再直出云端英文")
content_ts = read(path(SRC, "devices", "content.ts"))
ok("label: optionLabel(c.key, o.t)" in content_ts, "卡片快捷枚举芯片用中文名")
ok("label: o.t" not in content_ts, "卡片芯片不再直出英文")
ok("return onlineFirst(applyOrder(" in content_ts, "可见设备先按拖拽序、再按在线优先分区")

store_ts = read(path(SRC, "stores", "devices.ts"))
ok("navNodes" in store_ts, "房间切换器与侧栏共用 store.navNodes 一份层级")
for ep in ["/api/devices", "/api/live", "/api/layout", "/api/groups",
           "/api/history", "/api/switch", "/api/set"]:
    ok(ep in store_ts, "数据层覆盖后端端点 %s" % ep)
for needle in ["localStorage", "ver", "catch", "saveOrder("]:
    ok(needle in store_ts, "数据层具备 %s" % needle)

# ---- 5. 七层样式已实装且只用语义令牌 ----
STYLES = ["tokens.css", "base.css", "materials.css", "components.css",
          "instruments.css", "layout.css", "pages.css"]
style_text = {}
for name in STYLES:
    t = read(path(SRC, "styles", name))
    style_text[name] = t
    ok(len(t) > 1000, "第 %s 层 %s 已实装" % (STYLES.index(name) + 1, name))
    ok("此处先占位" not in t, "%s 不再是占位文件" % name)
all_css = "\n".join(style_text.values())
for legacy in ["var(--card)", "var(--dim)", "var(--text)", "var(--bg)",
               "var(--input)", "var(--radius", "var(--shadow", "var(--off)", "var(--mask)"]:
    ok(legacy not in all_css, "Vue 样式不引用旧界面令牌 %s" % legacy)

main_ts = read(path(SRC, "main.ts"))
order = [main_ts.find("styles/%s" % n) for n in STYLES]
ok(all(i >= 0 for i in order) and order == sorted(order), "七层引入顺序未被打乱")

comp_css = style_text["components.css"]
sw = re.search(r"\.mini-switch\s*\{([^}]*)\}", comp_css)
ok(bool(sw) and "position: relative" in sw.group(1),
   "mini-switch 宿主自成包含块（左上白圆点不复发）")
ok("position: static" not in comp_css, "组件层禁止 static 化旋钮宿主")
in_head = re.search(r"\.mini-switch\.in-head\s*\{([^}]*)\}", comp_css)
ok(bool(in_head) and "position: relative" in in_head.group(1),
   "头部开关同样保持 relative")
knob = re.search(r"\.mini-switch::after\s*\{([^}]*)\}", comp_css)
ok(bool(knob) and "position: absolute" in knob.group(1), "旋钮仍用绝对定位贴宿主")

lay_css = style_text["layout.css"]
grid_css = re.search(r"^\.grid\s*\{([^}]*)\}", lay_css, re.M)
ok(bool(grid_css), "第 6 层定义设备网格")
if grid_css:
    block = grid_css.group(1)
    ok("--card-row-h: 128px" in block, "网格固定 128px 行高")
    ok("grid-auto-rows: var(--card-row-h)" in block, "行高走局部变量而非 auto")
    ok("grid-auto-flow: dense" in block, "dense 自动填空隙")
    ok("--row-h" not in block, "表格密度令牌不参与卡片行高")
for needle in ["-webkit-line-clamp: 2", ".device-card.is-bare",
               '.device-card[data-category="light"]', "color-mix(in srgb, var(--cat)",
               ".drawer-layer", ".drawer-mask", ".rail {"]:
    ok(needle in lay_css, "外壳层保留 %s" % needle)

# 详情弹框：居中、双列、可滚动，外壳不再占满右侧
sheet_rule = re.search(r"\n\.sheet\s*\{([^}]*)\}", lay_css)
ok(bool(sheet_rule), "外壳层定义居中弹框 .sheet")
if sheet_rule:
    sheet_body = sheet_rule.group(1)
    ok("min(920px, 100%)" in sheet_body, "弹框定宽 920，窄屏自适应")
    ok("max-height" in sheet_body, "弹框有高度上限")
    ok("overflow: hidden" in sheet_body, "内容溢出交给内层滚动")
    ok("position: absolute" not in sheet_body and "right: 0" not in sheet_body,
       "不再贴在视口右侧")
layer_rule = re.search(r"\n\.drawer-layer\s*\{([^}]*)\}", lay_css)
ok(bool(layer_rule) and "justify-content: center" in layer_rule.group(1),
   "浮层用 flex 居中弹框")
body_rule = re.search(r"\n\.sheet-body\s*\{([^}]*)\}", lay_css)
ok(bool(body_rule), "外壳层定义弹框内容区")
if body_rule:
    body_block = body_rule.group(1)
    ok("grid-template-columns: 1fr 1fr" in body_block, "内容区双列等宽")
    ok("align-items: start" in body_block, "两列各自排布，行高不互相对齐")
ok(re.search(r"@media \(max-width: 760px\)\s*\{\s*\.sheet-body \{ grid-template-columns: 1fr;",
             lay_css) is not None, "窄屏收成一列")
# 家庭是一级、房间是二级：缺层级样式时两者渲染成同样的行，家庭分组等于消失
ok(".room-item.nav-home" in lay_css, "外壳层定义「全部设备」首项样式")
ok(".room-item.nav-room" in lay_css, "外壳层定义房间（二级）缩进")
nav_home = re.search(r"\.room-item\.nav-home\s*\{([^}]*)\}", lay_css)
ok(bool(nav_home) and "font-weight" in nav_home.group(1),
   "首项靠字重与房间区分")
nav_room = re.search(r"\.room-item\.nav-room\s*\{([^}]*)\}", lay_css)
ok(bool(nav_room) and "padding-left" in nav_room.group(1),
   "房间行左侧缩进")
# 顶栏房间切换：按钮 + 下拉菜单，层级语言与侧栏一致
for needle in [".hs-btn", ".hs-menu", ".hs-item.active", ".brand-txt",
               '.hs-btn[aria-expanded="true"]']:
    ok(needle in lay_css, "外壳层定义家庭切换 %s" % needle)
hs_menu = re.search(r"\.hs-menu\s*\{([^}]*)\}", lay_css)
ok(bool(hs_menu) and "position: absolute" in hs_menu.group(1),
   "家庭菜单浮在品牌行下方而非挤动侧栏")
# 顶栏动作组与外观浮层：右对齐、浮层从按钮下方展开
ok(".top-right" in lay_css and "margin-left: auto" in lay_css,
   "动作组靠右端对齐，不再挤在标签页后面")
ok(".top-actions" in lay_css, "外壳层定义顶栏动作组")
tp_menu = re.search(r"\.top-actions \.tp\s*\{([^}]*)\}", lay_css)
ok(bool(tp_menu) and "position: absolute" in tp_menu.group(1),
   "外观浮层浮在按钮下方而非挤动顶栏")
ok(bool(tp_menu) and "right: 0" in tp_menu.group(1), "外观浮层右缘对齐动作组")
ok(".rail-foot" not in lay_css, "外壳层不再保留侧栏底部动作区样式")
ok(".side-login" not in lay_css, "外壳层不再保留侧栏登录态文字样式")

pages_css = style_text["pages.css"]
for needle in [".login-stage", ".lp-cat", ".device-page", ".stat-strip"]:
    ok(needle in pages_css, "页面层同时承载登录页与设备页 %s" % needle)

# ---- 5b. 布局仪器化：统计条分格、侧栏滑块、底部铭牌 ----
ok(".stat-cell" in pages_css and ".stat-track" in pages_css,
   "统计条拆成读数格与在线率微槽")
ok(".stat-cell + .stat-cell" in pages_css, "读数格之间有发丝分隔线")
ok("repeat(var(--stat-cols, 3), minmax(88px, 1fr))" in pages_css,
   "读数格数量随类型分组变化，在线率格恒加宽")
ok(".stat-sub.hot" in pages_css, "「开 N」用强调色标出正在运行的台数")

# ---- 5c. 统计条只读当前范围，并按常用类型分组 ----
dev_store = read(path(SRC, "stores", "devices.ts"))
ok("statCounts(scoped.value, live.value)" in dev_store,
   "读数按当前家庭/房间/搜索范围统计，不再拿全屋家底充数")
ok("typeStats = computed(() => statGroups(scoped.value, live.value))" in dev_store,
   "类型读数同样跟随当前范围")
ok("filterByStat(scoped.value, statFilter.value)" in dev_store,
   "卡片 = 范围 + 统计筛选；读数仍按范围算，点筛选后条不塌")
ok("const scoped = computed(() => visibleDevices(" in dev_store,
   "范围单独成 computed，供统计与网格共用")
grid_src = read(path(SRC, "components", "DeviceGrid.vue"))
ok('v-for="g in store.typeStats"' in grid_src, "统计条按类型分组渲染")
ok("定时规则" not in grid_src and "schedRulesCount" not in grid_src,
   "统计条不再有定时规则格")
ok("--stat-cols" in grid_src, "格数由实际存在的分组决定")

# ---- 5d. 统计条可点：类型与在线都能一眼筛出对应卡片 ----
ok('class="stat-cell is-tap"' in grid_src, "计数格渲染成按钮（可点、可 Tab）")
ok(grid_src.count('store.toggleStatFilter(') >= 2, "在线格与类型格都接了切换")
ok('store.clearStatFilter()' in grid_src, "设备格与说明条都能一键回全部")
ok(':aria-pressed="isSel(' in grid_src and 'aria-pressed' in grid_src,
   "选中态同步给读屏（aria-pressed）")
ok("statFilter.value = ''" in dev_store and "function toggleStatFilter" in dev_store,
   "数据层：再点一次取消")
ok(".stat-cell.is-tap" in pages_css and ".stat-cell.is-sel" in pages_css,
   "可点格有 hover 与选中态样式")
ok("appearance: none" in pages_css and "font: inherit" in pages_css,
   "按钮重置成读数格的样子，不带 UA 边框与默认字族")
ok(".stat-strip .stat-cell + .stat-cell" in pages_css,
   "分隔线提高特异性，不被按钮的 border 重置吃掉")
ok(".stat-filter" in pages_css and ".sf-clear" in pages_css,
   "筛选中给出说明条与退出按钮")
# 换范围时筛选归零：进到没有该类设备的房间不该是空白
ok(dev_store.count("statFilter.value = ''") >= 3,
   "切家庭、切房间、清除各有一处归零")

# 窄屏统计条不拆两列：六格仍是一行，在线率独占第二行
stat_narrow = pages_css.split("@media (max-width: 760px) {", 1)[1] \
    .split("@media (max-width: 430px)", 1)[0]
ok("repeat(var(--stat-cols, 3), minmax(0, 1fr))" in stat_narrow,
   "窄屏按分组数排成一行，不再拆成两列")
ok("grid-template-columns: 1fr 1fr" not in stat_narrow,
   "统计条不再两列等分（那是详情弹框的事）")
ok("grid-column: 1 / -1" in stat_narrow and "border-left: 0" in stat_narrow,
   "在线率独占第二行，且不吃上一行留下的左分隔线")
ok("white-space: nowrap" in stat_narrow, "标签不换行，格子高度不会一高一低")
ok("@media (max-width: 430px)" in pages_css, "手机竖屏再紧一档，仍是单行")

ok(".nav-slider" in lay_css, "侧栏选中位由滑动竖条承担")
ok("position: absolute" in re.search(r"\.nav-slider\s*\{([^}]*)\}", lay_css).group(1),
   "竖条不参与布局，只做位移")
ok("inset 2px 0 0 var(--blue)" not in lay_css.split(".room-item.active")[1].split("}")[0],
   "选中项不再各画一条内阴影")
ok(".plate-bar" not in lay_css and ".pb-lamp" not in lay_css,
   "底部铭牌条整条拆除（样式一并清掉）")
ok("--plate-bg" not in read(path(ROOT, "web", "src", "styles", "tokens.css")),
   "铭牌专用令牌不留死代码")
ok("padding: 24px; max-width: 1520px" in read(path(ROOT, "web", "src", "App.vue")),
   "内容区不再给铭牌留 72px 空档")
ok("bottom: 24px" in style_text["components.css"], "提示条落回页底")
# 窄屏侧栏收起后，家庭切换必须还有入口，否则窄屏无法换家庭
app_src = read(path(ROOT, "web", "src", "App.vue"))
ok("top-home" in app_src and "<HomeSwitcher />" in app_src, "顶栏挂一份家庭切换")
ok(".top-home { display: none" in lay_css, "宽屏不重复出现第二个家庭入口")
ok(".top-home { display: block" in lay_css and ".top-crumb { display: none" in lay_css,
   "窄屏家庭接管最左、面包屑让位")
ok(".top-home .hs-menu { left: 0; right: auto" in lay_css, "顶栏菜单向左展开，不越出视口")
hs = read(path(ROOT, "web", "src", "components", "HomeSwitcher.vue"))
ok("m-glass-menu" in hs, "家庭菜单用更实的一档玻璃，不被底下读数透上来")

# ---- 6. 构建产物与文档 ----
vue_index = read(path(ROOT, "static", "vue", "index.html"))
ok("/static/vue/assets/" in vue_index, "产物入口指向 Flask 静态目录")
ok(os.path.isdir(path(ROOT, "static", "vue", "assets")), "构建资源目录存在")
readme = read(path(ROOT, "README.md"))
ok("④ 设备网格" in readme, "README 标注 ④ 设备网格")
ok("test_vue_devices.py" in readme, "README 登记新增测试")

print("\n通过 %d 项" % ok_n[0])
