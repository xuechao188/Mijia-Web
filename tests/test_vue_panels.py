#!/usr/bin/env python3
"""Vue 其余面板（步骤⑥）不变量：场景 / 自动化 / 日志 / 天气卡片。

1) 运行时交叉校验：Node 22 --experimental-strip-types 直接加载
   web/src/panels/*.ts，与旧界面 weather_card.js 的纯函数逐项比对，
   再验证散落在 static/app.js 里的文案、payload 形状与确认守卫。
2) 静态文本：组件接线、端点、样式钩子、旧前端零牵连。
"""
import json
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
    "panels/types.ts", "panels/weather.ts", "panels/scenes.ts",
    "panels/sceneIcons.ts", "panels/automations.ts", "panels/events.ts",
]

# ---- 1. 纯逻辑模块齐全 ----
for rel in PURE:
    ok(os.path.isfile(path(SRC, *rel.split("/"))), "新增 %s" % rel)

# ---- 2. 运行时交叉校验（Node 22 strip types） ----
with tempfile.TemporaryDirectory(prefix="vue_panels_") as tmp:
    # 场景图标复用设备图标，把 devices/icons.ts 一起搬进临时目录
    os.makedirs(path(tmp, "devices"), exist_ok=True)
    open(path(tmp, "devices", "icons.ts"), "w", encoding="utf-8").write(
        read(path(SRC, "devices", "icons.ts")))
    for rel in PURE:
        text = read(path(SRC, *rel.split("/")))
        # Vite 用无扩展名导入，Node ESM 解不开；测试副本补 .ts 后缀
        text = re.sub(r"from '\./([A-Za-z0-9_]+)'", r"from './\1.ts'", text)
        text = text.replace("from '../devices/icons'", "from './devices/icons.ts'")
        open(path(tmp, rel.split("/")[-1]), "w", encoding="utf-8").write(text)

    probe = r'''
const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
const [ROOT, TMP] = process.argv.slice(2);
const old = require(ROOT + '/static/weather_card.js');
const weather = await import('file://' + TMP + '/weather.ts');
const scenes = await import('file://' + TMP + '/scenes.ts');
const sceneIcons = await import('file://' + TMP + '/sceneIcons.ts');
const autos = await import('file://' + TMP + '/automations.ts');
const events = await import('file://' + TMP + '/events.ts');

let total = 0; const fail = [];
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
function push(msg, cond) { total++; if (!cond) fail.push(msg); }
function same(msg, a, b) { push(msg, eq(a, b)); }

/* ---------- 天气：与旧 weather_card.js 逐项同源 ---------- */
same('SIZES', old.SIZES, weather.SIZES);
same('SIZE_LABELS', old.SIZE_LABELS, weather.SIZE_LABELS);
const codes = [-9, -1, 0, 1, 2, 3, 4, 45, 48, 50, 51, 53, 55, 61, 65, 67,
               70, 71, 73, 75, 77, 80, 81, 82, 85, 86, 94, 95, 96, 97, 99,
               100, 200, '0', '3', '61', '', null, undefined, 'abc'];
for (const c of codes) same('kindOf ' + String(c), old.kindOf(c), weather.kindOf(c));
const kinds = ['sun', 'partly', 'cloud', 'fog', 'rain', 'snow', 'storm', 'other'];
for (const k of kinds) {
  for (const px of [undefined, 22, 40, 1]) {
    same('iconSvg ' + k + '/' + px, old.iconSvg(k, px), weather.iconSvg(k, px));
  }
}
const aqis = [null, undefined, '', 'abc', NaN, Infinity, -1, 0, 1, 19.6, 20,
              21, 40, 41, 60, 80, 100, 101, 250, '35'];
for (const a of aqis) same('aqiGrade ' + String(a), old.aqiGrade(a), weather.aqiGrade(a));
for (const s of ['sm', 'md', 'lg', 'xx', undefined, null]) {
  same('fieldsFor ' + String(s), old.fieldsFor(s), weather.fieldsFor(s));
}
const nums = [null, undefined, '', 'abc', NaN, Infinity, 0, 1, -2.4, 3.6,
              '12.34', '0', 23.55, -0.5];
for (const v of nums) {
  same('tempText ' + String(v), old.tempText(v), weather.tempText(v));
  same('tempText1 ' + String(v), old.tempText(v, 1), weather.tempText(v, 1));
  same('tempText2 ' + String(v), old.tempText(v, 2), weather.tempText(v, 2));
  same('pctText ' + String(v), old.pctText(v), weather.pctText(v));
}
const ws = [
  null, undefined, {},
  { code: 3, unavailable: true, text: '天气暂不可用', city: '合肥' },
  { city: '合肥', temp: 24.3, feels: 26, code: 2, text: '多云', wind: 9,
    aqi: 33, humidity: 61, is_day: 0, updated: '08:30', stale: true,
    today: { tmax: 28, tmin: 18, sunrise: '06:12', sunset: '17:40', pop_max: 20 },
    hourly: [{ time: '08:00', temp: 22, pop: 10 }, { time: '09:00', temp: null, pop: 20 },
             { time: '10:00', temp: 25, pop: 30 }, { time: '11:00', temp: 26, pop: 0 },
             { time: '12:00', temp: '27', pop: null }, { time: '13:00', temp: 28, pop: 40 }] },
  { hourly: null, today: null, aqi: null, stale: false },
];
const full24 = { hourly: Array.from({ length: 24 }, (_, i) => ({
  time: String(i).padStart(2, '0') + ':00', temp: 10 + i * 0.5, pop: i, code: 0,
})) };
ws.push(full24);
for (let i = 0; i < ws.length; i++) {
  const w = ws[i];
  same('hourlySeries ' + i, old.hourlySeries(w), weather.hourlySeries(w));
  same('hourlyLabels ' + i, old.hourlyLabels(w), weather.hourlyLabels(w));
  same('tempRange ' + i, old.tempRange(w), weather.tempRange(w));
  for (const s of ['sm', 'md', 'lg']) {
    const f = weather.fieldsFor(s);
    push('weatherMetrics ' + i + '/' + s,
      weather.weatherMetrics(w, f).length ===
      f.filter((k) => ['feels', 'range', 'aqi', 'wind', 'humidity', 'pop', 'sun'].includes(k)).length);
  }
  push('weatherCardClass ' + i,
    weather.weatherCardClass(w, 'md').includes('wc-' + weather.kindOf(w && w.code)));
  push('weatherFoot ' + i, typeof weather.weatherFoot(w) === 'string');
  push('weatherHero ' + i, weather.weatherHero(w).includes('体感'));
  same('drawerReadouts ' + i, weather.drawerReadouts(w).length, 8);
  push('hourStrip ' + i,
    weather.hourStrip(w).length === Math.ceil(((w && w.hourly) || []).length / 3));
}
push('weatherCardClass 夜间', weather.weatherCardClass({ is_day: 0 }, 'sm').includes('wc-night'));
same('weatherFoot 不可用', weather.weatherFoot(ws[3]), '天气暂不可用 · 稍后自动重试');
same('weatherFoot 陈旧', weather.weatherFoot(ws[4]), '数据未更新');
same('weatherFoot 更新于', weather.weatherFoot({ updated: '08:30' }), '更新于 08:30');
push('WEATHER_FALLBACK 保留骨架', weather.WEATHER_FALLBACK.unavailable === true);

/* ---------- 场景 ---------- */
const scene = { scene_id: '987', name: '回家模式', home_id: '123', owner_uid: 42 };
same('sceneLabel', scenes.sceneLabel(scene), '回家模式');
same('sceneLabel 无名字', scenes.sceneLabel({ scene_id: '9', name: '', home_id: '1' }), '场景9');
same('runPayload', scenes.runPayload(scene),
  { scene_id: '987', home_id: '123', owner_uid: 42, name: '回家模式' });
same('runToast 成功', scenes.runToast({ ok: true }, scene), '场景已执行：回家模式');
same('runToast 失败带错', scenes.runToast({ ok: false, error: '云端不通' }, scene), '云端不通');
same('runToast 失败无错', scenes.runToast({ ok: false }, scene), '场景执行失败');

/* ---------- 场景图标与同名编号 ---------- */
const iconKinds = [['灯全关', 'light'], ['窗帘全开', 'curtain'], ['打开空调', 'climate'],
               ['离家模式', 'away'], ['回家', 'home'], ['睡觉灯光', 'moon'],
               ['早安模式', 'sun'], ['看个电影', 'film'], ['随便写写', 'bolt'],
               ['', 'bolt'], ['  ', 'bolt']];
for (const [n, k] of iconKinds) {
  push('sceneKind 「' + (n || '(空)') + '」→ ' + k, sceneIcons.sceneKind(n) === k);
}
const ssvg = sceneIcons.sceneIcon('窗帘全开');
push('sceneIcon 输出 svg 根', ssvg.startsWith('<svg') && ssvg.includes('viewBox="0 0 24 24"'));
push('sceneIcon 根 fill=none（不被主题染实心）', ssvg.includes('fill="none"'));
push('sceneIcon 未知名称也有一枚图标', sceneIcons.sceneIcon('???').includes('<path'));
push('sceneIcon 复用设备图标：窗帘与设备同一条 path',
  ssvg.includes('M3 3.6h18'));
const dup = scenes.dupeIndex([
  { scene_id: 'a', name: '灯全关', home_id: '1' },
  { scene_id: 'b', name: '灯全关', home_id: '1' },
  { scene_id: 'c', name: '回家', home_id: '1' },
  { scene_id: 'd', name: '灯全关', home_id: '2' },
]);
same('dupeIndex 第 2、3 条同名才有号', dup, { b: 2, d: 3 });
same('dupeIndex 空列表', scenes.dupeIndex([]), {});
same('dupeIndex 首条不编号', dup.a, undefined);

/* ---------- 自动化 ---------- */
const items = [
  { scene_id: 'a1', name: '门厅 有人到访', home_name: '信地', enable: true,
    counts: { trigger: 1, condition: 0, action: 2 }, summary: '当 门铃…',
    update_time: '1700000000', triggers: [{ device: '门铃', name: '有人按门铃' }],
    actions: [{ device: '灯', name: '开灯', value: true }, { device: '音箱', key: '播报' }],
    raw: { scene_id: 'a1' } },
  { scene_id: 'a2', name: '空触发', home_name: '信地', enable: false,
    counts: { trigger: 0, condition: 1, action: 1 } },
  { scene_id: 'a3', name: '无动作', home_name: '合肥', enable: true,
    counts: { trigger: 2, condition: 0, action: 0 } },
];
same('usableTemplates', autos.usableTemplates(items).map((a) => a.scene_id), ['a1']);
same('templateSignature', autos.templateSignature(items), 'a1');
same('countText', autos.countText(3, 2), '3 条 · 启用 2');
same('headText', autos.headText('信地', 3, 2), '信地 · 3 条 · 启用 2');
same('headText 无家庭名', autos.headText('', 3, 2), '3 条 · 启用 2');
same('emptyText', autos.emptyText('信地'), '信地 还没有自动化');
same('emptyText 无家庭名', autos.emptyText(''), '当前家庭 还没有自动化');
push('不再保留跨家庭分组 helper：列表只列当前家庭',
  typeof autos.groupByHome === 'undefined' && typeof autos.homeLabel === 'undefined');
same('autoMeta', autos.autoMeta(items[0]), '触发 1 · 条件 0 · 动作 2');
same('templateOptionText 启用', autos.templateOptionText(items[0]), '启用 · 门厅 有人到访');
same('templateOptionText 停用', autos.templateOptionText(items[1]), '停用 · 空触发');
same('createFormPayload', autos.createFormPayload('  客厅灯  ', 'a1', false),
  { template_scene_id: 'a1', name: '客厅灯', enable: false });
same('createFormPayload 空模板', autos.createFormPayload('x', '', true),
  { template_scene_id: '', name: 'x', enable: true });
const cf = { template_scene_id: 'a1', name: '客厅灯', enable: false };
same('createConfirmText', autos.createConfirmText(cf, '门厅 有人到访'),
  '将复制「门厅 有人到访」的触发、条件与动作，新建一条自动化：\n\n' +
  '名称：客厅灯\n状态：停用（推荐）\n\n改动会同步到米家 App 与家庭共享成员，确认创建？');
same('createConfirmText 立即启用', autos.createConfirmText({ ...cf, enable: true }, ''),
  '将复制「a1」的触发、条件与动作，新建一条自动化：\n\n' +
  '名称：客厅灯\n状态：立即启用\n\n改动会同步到米家 App 与家庭共享成员，确认创建？');
same('applyConfirmText 改名', autos.applyConfirmText({ name: '新名' }),
  '把自动化名称改为「新名」并同步到米家云端？');
same('applyConfirmText 启用', autos.applyConfirmText({ enable: true }),
  '启用这条自动化？改动会同步到米家 App 和家人设备。');
same('applyConfirmText 停用', autos.applyConfirmText({ enable: false }),
  '停用这条自动化？改动会同步到米家 App 和家人设备。');
same('deleteConfirmText', autos.deleteConfirmText('门厅 有人到访'),
  '将永久删除自动化「门厅 有人到访」？\n\n' +
  '此操作不可撤销，米家 App 与家庭共享成员处都会消失。');
push('deleteNameMatch 一致', autos.deleteNameMatch('门厅 有人到访', items[0]));
push('deleteNameMatch 不一致', !autos.deleteNameMatch('门厅', items[0]));
same('detailBlocks 顺序', autos.detailBlocks(items[0]).map((b) => b[0]),
  ['触发', '条件', '执行', '否则']);
same('detailBlocks 数量', autos.detailBlocks(items[0]).map((b) => b[1].length), [1, 0, 2, 0]);
same('entryDevice', autos.entryDevice({}), '—');
same('entryName key 兜底', autos.entryName({ key: 'power' }), 'power');
same('entryValue 布尔', autos.entryValue({ value: true }), '值 true');
same('entryValue 空', autos.entryValue({ value: '' }), '');
same('entryValue undefined', autos.entryValue({}), '');
push('updateTimeText 数值', autos.updateTimeText({ update_time: '1700000000' }).includes('2023'));
same('updateTimeText 空', autos.updateTimeText({}), '—');
same('updateTimeText 非法', autos.updateTimeText({ update_time: 'abc' }), '—');
push('detailHead', autos.detailHead(items[0]).includes('信地 · 已启用 · 更新于 '));
same('createOutput 成功', autos.createOutput({ ok: true, result: { id: 1 }, created_id: 'n1' }),
  '创建成功，云端返回：{"id":1}\n新 scene_id：n1');
same('createOutput 失败', autos.createOutput({ ok: false, error: '云端拒绝' }), '创建失败：云端拒绝');
same('applyOutput 成功', autos.applyOutput({ ok: true, result: {}, preview: { changes: ['name'] } }),
  '写入成功，云端返回：{}\n改动内容：[\n  "name"\n]');
same('applyOutput 失败', autos.applyOutput({ ok: false }), '写入失败：未知错误');
same('deleteOutput 失败', autos.deleteOutput({ ok: false, error: 'x' }), '删除失败：x');
same('previewOutput 成功', autos.previewOutput({ ok: true, preview: { a: 1 } }),
  autos.previewText({ a: 1 }));
push('预览无改动时直说，不再丢一个 patch 字段给人猜',
  autos.previewText({ a: 1 }).includes('改动 0 项（与云端现有内容一致）'));
same('previewOutput 失败', autos.previewOutput({ ok: false, error: '未找到' }), '未找到');
const pv = autos.previewText({
  operation: 'edit', uri: '/home/automation/edit',
  changes: [{ field: 'name', from: '旧名', to: '新名' },
            { field: 'enable', from: true, to: false }],
  payload: { name: '新名' },
});
push('预览首行说清端点', pv.startsWith('将要发送：修改 · 端点 /home/automation/edit'));
push('预览把机器字段翻成中文', pv.includes('名称：旧名 → 新名') &&
  pv.includes('状态：启用 → 停用'));
push('预览保留完整请求体', pv.includes('完整请求体（JSON）：') &&
  pv.includes('"name": "新名"'));
push('预览明确只是本地生成', pv.includes('这一段只是预览'));
push('新建预览标注操作类型', autos.previewText({ operation: 'create', changes: [] })
  .startsWith('将要发送：新建'));
push('删除预览标注操作类型', autos.previewText({ operation: 'delete', changes: [] })
  .startsWith('将要发送：删除'));
push('无改动时前端先拦住', autos.PREVIEW_NEED_CHANGE.includes('当前没有改动'));

/* ---------- 事件流 ---------- */
const evt = { time: '11-15 08:00:00', type: 'error', name: '客厅灯', text: '已关闭' };
same('eventTime', events.eventTime(evt), '11-15 08:00:00');
same('eventText', events.eventText(evt), '[客厅灯] 已关闭');
same('eventText 无设备名', events.eventText({ text: '同步完成' }), '同步完成');
same('eventTone error', events.eventTone(evt), 'err');
same('eventTone 普通', events.eventTone({ type: 'scene' }), '');
same('summaryText', events.summaryText({ scene: 2, error: 1 }), 'error 1 · scene 2');
same('summaryText 空', events.summaryText({}), '');

console.log(JSON.stringify({ total: total, fail: fail }));
'''
    probe_path = path(tmp, "probe_panels.mjs")
    with open(probe_path, "w", encoding="utf-8") as f:
        f.write(probe)
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
            payload = json.loads(line)
    ok(payload.get("fail") == [], "Node 运行时交叉校验 %s 项全过：%s" % (
        payload.get("total", 0), (payload.get("fail") or [])[:6]))
    for _ in range(int(payload.get("total", 0))):
        ok_n[0] += 1

# ---- 3. 旧界面文案与端点同源 ----
app_js = read(path(ROOT, "static", "app.js"))
index_html = read(path(ROOT, "static", "index.html"))
for needle in ["/api/scenes", "/api/scenes/run", "/api/automations",
               "/api/automations/detail", "/api/automations/preview",
               "/api/automations/apply", "/api/automations/create",
               "/api/automations/create/preview", "/api/automations/delete",
               "/api/automations/delete/preview", "/api/events", "/api/weather",
               "confirm: true", "setInterval(loadEvents, 15000)",
               "setInterval(loadWeather, 600000)", "setInterval(loadScenes, 300000)"]:
    ok(needle in app_js, "旧界面存在同源端点/调度 %s" % needle)
for needle in [
    "支持改名、启停、新建与删除；写入均需二次确认，删除需手动输入完整名称复核。",
    "创建会同步到米家 App 与家庭共享成员；删除不可撤销。",
    "新建自动化 · 复制现有自动化的触发、条件与动作",
]:
    ok(needle in index_html, "旧界面存在同源文案 %s" % needle[:16])

weather_ts = read(path(SRC, "panels", "weather.ts"))
autos_ts = read(path(SRC, "panels", "automations.ts"))
for needle in ["AUTO_NOTE", "CREATE_DANGER", "CREATE_TITLE", "confirm", "deleteNameMatch"]:
    ok(needle in autos_ts, "自动化纯逻辑含 %s" % needle)
ok("欧洲 AQI" in weather_ts or "欧洲" in weather_ts, "天气分档沿用欧洲 AQI 口径")

# ---- 4. 组件、数据层与外壳接线 ----
FILES = [
    "components/ScenesPanel.vue", "components/AutomationsPanel.vue",
    "components/AutomationDrawer.vue", "components/EventsPanel.vue",
    "components/WeatherCard.vue", "components/WeatherDrawer.vue",
    "stores/panels.ts",
]
text = {}
for rel in FILES:
    text[rel] = read(path(SRC, *rel.split("/")))
    ok(len(text[rel]) > 700, "新增/改造 %s" % rel)

app_vue = read(path(SRC, "App.vue"))
for name in ["ScenesPanel", "AutomationsPanel", "AutomationDrawer", "EventsPanel",
             "WeatherDrawer", "usePanelsStore", "panels.bootstrap()",
             "panels.startPolling()", "panels.stopPolling()", "closePanelDrawers()"]:
    ok(name in app_vue, "App.vue 接入 %s" % name)
ok("panel-soon" not in app_vue, "⑥ 占位面板已移除")
ok("⑦ 验收" not in app_vue and 'class="steps' not in app_vue,
   "验收完成后移除页面底部的迁移进度条")
ok("auth.phase !== 'app'" in app_vue, "未登录时登录页仍是唯一内容")

grid_vue = read(path(SRC, "components", "DeviceGrid.vue"))
for needle in ["WeatherCard", "usePanelsStore", "showWeather",
               "panels.weatherSize"]:
    ok(needle in grid_vue, "DeviceGrid 接线 %s" % needle)

scene_vue = text["components/ScenesPanel.vue"]
for needle in ["store.runScene(", "scene-btn", "SCENE_EMPTY", "sceneLabel("]:
    ok(needle in scene_vue, "ScenesPanel 接线 %s" % needle)
# ⑦ 场景砖：放大 + 图标 + 按下动效
for needle in ["scene-tile", "st-ico", "st-go", "st-spin", "dupeIndex(",
               "sceneIcon(", "scenePress(", "sceneSettle(", "@pointerdown",
               "const ok = await store.runScene(s)"]:
    ok(needle in scene_vue, "场景砖接线 %s" % needle)
ok("rip.className = 'st-ripple'" in read(path(SRC, "motion", "index.ts")),
   "水波节点由动效层注入（模板里没有多余节点）")
ok("if (ok) sceneSettle(el)" in scene_vue, "只有执行成功才给「收到」反馈")
panels_store = read(path(SRC, "stores", "panels.ts"))
ok("async function runScene(s: SceneItem): Promise<boolean>" in panels_store,
   "runScene 回报成败，界面不做假成功")
ok("ok = Boolean(r.ok)" in panels_store, "成败取自后端 ok 字段")

auto_vue = text["components/AutomationsPanel.vue"]
for needle in ["window.confirm(createConfirmText(", "store.createAutomation(",
               "store.previewCreate(", "store.toggleAutoCreate()",
               "usableTemplates(", "scopedAutomations", "headText(", "emptyText(",
               "auto-new-template", "预览请求内容", "previewOutput(",
               "store.openAutoDetail(", "AUTO_NOTE", "CREATE_DANGER"]:
    ok(needle in auto_vue, "AutomationsPanel 接线 %s" % needle)
ok("查看 payload" not in auto_vue, "新建表单不再用「payload」这种黑话")
# 列表不再折叠：标题纯文字，无折叠开关、无内嵌滚动
ok("toggleAutoOpen" not in auto_vue and "auto-toggle" not in auto_vue,
   "自动化列表不再折叠")
ok(auto_vue.count("v-for=\"a in items\"") == 1,
   "条目直接铺在当前家庭列表里，没有一层分组循环")

auto_drawer = text["components/AutomationDrawer.vue"]
for needle in ["window.confirm(applyConfirmText(", "window.confirm(deleteConfirmText(",
               "store.applyEdit(", "store.deleteAutomation(", "store.previewEdit(",
               "store.previewDelete(", "previewOutput(", "PREVIEW_NEED_CHANGE",
               "预览请求内容", "detailBlocks(", "auto-delete-name",
               "store.autoWritable", "store.autoDeleteSupported"]:
    ok(needle in auto_drawer, "AutomationDrawer 接线 %s" % needle)
ok("查看 payload" not in auto_drawer, "详情弹框不再用「payload」这种黑话")
ok("Object.keys(patch).length" in auto_drawer,
   "没改动时前端就拦住预览，不拿空 patch 去请求后端")
# 三个详情统一成居中双列弹框
for name, src in [("Auto", auto_drawer), ("Weather", text["components/WeatherDrawer.vue"]),
                  ("Device", read(path(SRC, "components", "DeviceDrawer.vue")))]:
    ok('<div class="sheet m-glass m-glass-strong"' in src, name + " 详情是居中弹框")
    ok(src.count('class="sheet-col"') == 2, name + " 详情分左右两列")
    ok("<aside" not in src, name + " 不再用侧滑抽屉外壳")
ok(auto_drawer.index('class="dr-panel m-surface auto-edit"')
   < auto_drawer.index('m-surface auto-danger'),
   "自动化：写入在左列之上、删除在下，只读明细单独一列")

event_vue = text["components/EventsPanel.vue"]
for needle in ["eventText(", "eventTime(", "eventTone(", "event-list"]:
    ok(needle in event_vue, "EventsPanel 接线 %s" % needle)
ok("v-html" not in event_vue, "事件文案只用插值，杜绝特殊字符注入")

weather_card = text["components/WeatherCard.vue"]
for needle in ["weatherCardClass(", "fieldsFor(", "weatherMetrics(", "iconSvg(",
               "sparkline(", "wc-sizes", "openWeatherDrawer()", "data-widget"]:
    ok(needle in weather_card, "WeatherCard 接线 %s" % needle)

weather_drawer = text["components/WeatherDrawer.vue"]
for needle in ["drawerReadouts(", "hourStrip(", "sparkline(", "setWeatherCity(",
               "setWeatherSize(", "WEATHER_NOTE", "wc-city"]:
    ok(needle in weather_drawer, "WeatherDrawer 接线 %s" % needle)

# 天气卡是全局信息：filter 会被 validFilter 校准成「当前家庭」，
# 只认字面 'all' 会让卡与详情入口永远出不来
dev_grid = read(path(SRC, "components", "DeviceGrid.vue"))
ok("parseKey(store.filter).type" in dev_grid, "天气卡按筛选类型判断可见性")
ok("store.filter === 'all'" not in dev_grid, "天气卡不再被校准后的 filter 卡死")
ok("t === 'all' || t === 'home'" in dev_grid, "家庭一层显示、进房间后让出首格")

# ---- 5. 数据层：端点、写入守卫、轮询与抽屉互斥 ----
panels_ts = text["stores/panels.ts"]
for ep in ["/api/scenes", "/api/scenes/run", "/api/automations",
           "/api/automations/detail", "/api/automations/preview",
           "/api/automations/apply", "/api/automations/create/preview",
           "/api/automations/create", "/api/automations/delete/preview",
           "/api/automations/delete", "/api/events", "/api/weather"]:
    ok(ep in panels_ts, "面板数据层覆盖端点 %s" % ep)
for needle in ["confirm: true", "deleteNameMatch(", "closePanelDrawers",
               "closeOtherDrawers()", "EVENTS_POLL_MS = 15000",
               "SCENES_POLL_MS = 300000", "AUTOS_POLL_MS = 300000",
               "WEATHER_POLL_MS = 600000",
               "loadAutomations(true)", "[...(r.scenes || [])]"]:
    ok(needle in panels_ts, "面板数据层具备 %s" % needle)
ok("detail.loadRules" not in panels_ts and "schedRulesCount" not in panels_ts,
   "面板数据层不再拉取定时规则")
ok(panels_ts.count("confirm: true") >= 3, "三条写入链路都显式带 confirm=true")
ok("fetch(" not in auto_vue and "fetch(" not in weather_drawer,
   "面板组件不绕过数据层直接发请求")

# ---- 6. 后端与旧前端零牵连 ----
for rel, needle in [
    ("routes/scenes.py", '@bp.route("/api/scenes")'),
    ("routes/misc.py", '@bp.route("/api/events")'),
    ("routes/automations.py", '@bp.route("/api/automations")'),
]:
    ok(needle in read(path(ROOT, *rel.split("/"))), "后端 %s 保持原样" % rel)
old_index = read(path(ROOT, "static", "index.html"))
for needle in ["scene-panel", "automation-panel", "event-panel", "weather_card.js"]:
    ok(needle in old_index, "旧界面 %s 入口未被删除" % needle)
old_app = read(path(ROOT, "static", "app.js"))
ok("查看 payload" not in old_index and "查看 payload" not in old_app,
   "旧界面的预览按钮也换成直白说法")
ok("当前没有改动" in old_app, "旧界面同样先拦住空 patch 预览")
backend_auto = read(path(ROOT, "services", "automations.py"))
ok("没有任何改动（patch 为空）" in backend_auto,
   "后端把空 patch 说成「没有任何改动」，不再只报字段名")

# ---- 7. 七层样式与语义令牌 ----
styles = ["tokens.css", "base.css", "materials.css", "components.css",
          "instruments.css", "layout.css", "pages.css"]
css = {n: read(path(SRC, "styles", n)) for n in styles}
all_css = "\n".join(css.values())
for legacy in ["var(--card)", "var(--dim)", "var(--text)", "var(--bg)",
               "var(--input)", "var(--radius", "var(--shadow", "var(--off)",
               "var(--mask)", "var(--danger)", "var(--on-glow)"]:
    ok(legacy not in all_css, "Vue 样式不引用旧界面令牌 %s" % legacy)
for needle in [".btn.danger", ".scene-btn", ".auto-list", ".auto-item",
               ".auto-create", ".auto-payload", ".auto-danger", ".event-list",
               ".weather-card", ".wc-size", ".wc-metrics", ".wc-chart",
               ".wc-hero", ".wc-hours", ".wc-settings"]:
    ok(needle in all_css, "样式钩子 %s 已实装" % needle)
ok(".auto-toggle" not in all_css and ".auto-chevron" not in all_css,
   "折叠开关的样式已随功能删除")
ok("max-height" not in css["layout.css"].split(".auto-list {")[1].split("}")[0],
   "自动化列表不再限高，由页面整体滚动")
for needle in [".scene-tile", ".st-ico", ".st-text", ".st-go", ".st-ripple",
               ".st-spin"]:
    ok(needle in all_css, "场景砖样式 %s 已实装" % needle)
ok("@keyframes st-spin" not in all_css,
   "转圈不写成 CSS infinite：动效只经 motion/，减弱动效时才有得停")
ok("min-height: 68px" in css["components.css"], "场景砖比普通按钮高一档（68px）")
ok("grid-template-columns: repeat(auto-fill, minmax(208px, 1fr))" in css["layout.css"],
   "场景砖等宽栅格排布，不再参差换行")
ok("spin(" in read(path(SRC, "components", "ScenesPanel.vue")),
   "场景转圈由动效层启停")
ok("animation:" not in css["components.css"].split(".st-spin {")[1].split("}")[0],
   "转圈本身不带 CSS 动画")
ok('.sheet[aria-label="天气详情"] .dr-readout-v' in css["pages.css"],
   "天气弹框长读数允许换行，不被省略号截断")
ok("position: static" not in css["components.css"], "④ 的旋钮宿主修复未被破坏")
ok(".sched-rule" not in css["layout.css"], "定时规则卡样式已随功能删除")
main_ts = read(path(SRC, "main.ts"))
order = [main_ts.find("styles/%s" % n) for n in styles]
ok(all(i >= 0 for i in order) and order == sorted(order), "七层引入顺序未被打乱")

# ---- 8. 构建产物与文档 ----
ok(os.path.isfile(path(ROOT, "static", "vue", "index.html")), "Vue 构建入口仍在")
ok("/static/vue/assets/" in read(path(ROOT, "static", "vue", "index.html")),
   "产物入口指向 Flask 静态目录")
readme = read(path(ROOT, "README.md"))
ok("⑥ 其余面板 | 完成" in readme, "README 标注 ⑥ 完成")
ok("test_vue_panels.py" in readme, "README 登记新增测试")

print("\n通过 %d 项" % ok_n[0])
