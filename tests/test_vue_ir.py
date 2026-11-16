#!/usr/bin/env python3
"""红外遥控前端不变量（Vue + 旧界面同源）。

红外设备的控制面是「命令按钮」而不是开关/滑杆，所以卡片与详情走的是另一套：
  - 分类必须落在 ir（不能掉进 light / aircondition / hub）
  - 卡片尺寸看「有没有命令或按键」，空遥控器不该占中卡
  - 卡片副标题写「电视遥控 · 97 键」，不写「状态未知」
  - 按钮一发即走，没有选中态（红外没有状态，画选中态就是伪造）
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
    "devices/types.ts", "devices/cards.ts", "devices/icons.ts",
    "devices/groups.ts", "devices/readouts.ts", "devices/content.ts",
    "devices/labels.ts",
]

for rel in PURE:
    ok(os.path.isfile(path(SRC, *rel.split("/"))), "纯模块存在 %s" % rel)

with tempfile.TemporaryDirectory(prefix="vue_ir_") as tmp:
    for rel in PURE:
        text = read(path(SRC, *rel.split("/")))
        text = re.sub(r"from '\./([A-Za-z]+)'", r"from './\1.ts'", text)
        open(path(tmp, rel.split("/")[-1]), "w", encoding="utf-8").write(text)

    probe = r'''
const { createRequire } = await import('node:module');
const require = createRequire(import.meta.url);
const [ROOT, TMP] = process.argv.slice(2);
const J = (p) => require(ROOT + '/static/' + p);
const oldCards = J('cards.js');
const oldIcons = J('device_icons.js');
const oldTypes = J('card_types.js');
const cards = await import('file://' + TMP + '/cards.ts');
const icons = await import('file://' + TMP + '/icons.ts');
const content = await import('file://' + TMP + '/content.ts');

const checks = [];
const push = (name, v) => checks.push([name, !!v]);
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

function dev(o) {
  return Object.assign({
    did: 'd1', name: '设备', model: '', product: '', home: '', room: '',
    online: true, controls: [], readable: {}, switches: [],
  }, o || {});
}
const key = (id, name) => ({ id, name });
const cmd = (o) => Object.assign({
  id: 'a:2:1', kind: 'action', group: '电源', label: '开机', siid: 2, aiid: 1,
}, o || {});

const TV_CMDS = [
  cmd({ id: 'a:2:2', label: '开机', name: 'turn-on' }),
  cmd({ id: 'a:2:1', label: '关机', name: 'turn-off' }),
  cmd({ id: 'a:2:3', group: '音量', label: '音量 ＋', name: 'volume-up' }),
  cmd({ id: 'a:2:4', group: '音量', label: '音量 －', name: 'volume-down' }),
  cmd({ id: 'a:2:5', group: '静音', label: '静音', name: 'mute-on' }),
];
const AC_CMDS = [
  cmd({ id: 'a:2:6', label: '开机', name: 'turn-on' }),
  cmd({ id: 'p:2:1:1', kind: 'set', group: '模式', label: '制冷', siid: 2, piid: 1, value: 1 }),
];
// 温度不进命令表：它是 ir 块上的步进（－ 26°C ＋）
const AC_TEMP = { siid: 2, piid: 2, min: 16, max: 30, step: 1, default: 26 };

const tv = dev({ did: 'ir.1', name: '电视遥控', model: 'miir.tv.ir01',
  ir: { kind: 'tv', label: '电视遥控', cmds: TV_CMDS,
        keys: [key(1, '电源'), key(2, '静音'), key(3, '信号源')], note: '单向发码' } });
const ac = dev({ did: 'ir.2', name: '空调遥控', model: 'miir.aircondition.ir02',
  ir: { kind: 'ac', label: '空调遥控', cmds: AC_CMDS, keys: [], temp: AC_TEMP, note: '单向发码' } });
const custom = dev({ did: 'ir.3', name: '床', model: 'miir.remote.ir01',
  ir: { kind: 'remote', label: '自定义遥控', cmds: [],
        keys: [key(7, '上升'), key(8, '暂停'), key(9, '下降')], note: '单向发码' } });
const empty = dev({ did: 'ir.4', name: '空遥控', model: 'miir.remote.ir01',
  ir: { kind: 'remote', label: '自定义遥控', cmds: [], keys: [], note: '' } });
const lamp = dev({ did: 'ir.5', name: '床头灯', model: 'miir.light.ir01',
  ir: { kind: 'light', label: '灯具遥控', cmds: TV_CMDS.slice(0, 4), keys: [], note: '单向发码' } });
const offTv = dev({ did: 'ir.6', name: '电视遥控', model: 'miir.tv.ir01', online: false,
  ir: { kind: 'tv', label: '电视遥控', cmds: TV_CMDS, keys: [key(1, '电源')], note: '' } });
const irs = [tv, ac, custom, empty, lamp, offTv];

// ---- 分类：红外不能被 light / aircondition / hub 抢走 ----
for (const d of irs) {
  push('categoryOf(' + d.model + ') 是 ir', cards.categoryOf(d) === 'ir');
  push('categoryOf(' + d.model + ') 与旧版一致', oldCards.categoryOf(d) === cards.categoryOf(d));
}
push('CATEGORY_LABELS.ir 存在且为中文', cards.CATEGORY_LABELS.ir === '红外遥控');
push('CATEGORY_LABELS 与旧版一致', eq(oldCards.CATEGORY_LABELS, cards.CATEGORY_LABELS));
push('红外不算可开关品类', irs.every((d) => cards.toggleable(d) === false));
push('toggleable 与旧版一致', irs.every((d) => oldCards.toggleable(d) === cards.toggleable(d)));
push('红外归到统计条「其它」', irs.every((d) => cards.statGroupOf(d) === 'other'));

// 普通设备不能被新规则误判
push('普通灯具仍是 light', cards.categoryOf(dev({ model: 'yeelink.light.lamp1' })) === 'light');
push('实体空调仍是 climate', cards.categoryOf(dev({ model: 'xiaomi.aircondition.mc1' })) === 'climate');
push('网关仍是 hub', cards.categoryOf(dev({ model: 'lumi.gateway.mgl03' })) === 'hub');

// ---- 尺寸：有按钮才占中卡 ----
push('电视遥控是中卡', cards.sizeOf(tv) === 'md');
push('空调遥控是中卡', cards.sizeOf(ac) === 'md');
push('自定义遥控（有按键）是中卡', cards.sizeOf(custom) === 'md');
push('空遥控器收成单格', cards.sizeOf(empty) === 'sm');
push('离线红外收成单格（按钮根本点不了）', cards.sizeOf(offTv) === 'sm');
push('sizeOf 与旧版一致', irs.every((d) => oldCards.sizeOf(d) === cards.sizeOf(d)));
push('irActionCount 命令优先', cards.irActionCount(tv) === TV_CMDS.length
  && cards.irActionCount(custom) === 3 && cards.irActionCount(empty) === 0);

// ---- 快捷按钮：命令优先，没有命令表就用按键 ----
push('电视遥控卡片前 4 个按钮是命令',
  eq(content.irQuick(tv).map((c) => c.label), ['开机', '关机', '音量 ＋', '音量 －']));
push('自定义遥控退回按键，并标成 kind=key',
  eq(content.irQuick(custom).map((c) => c.label), ['上升', '暂停', '下降'])
  && content.irQuick(custom).every((c) => c.kind === 'key' && c.key_id));
push('没有命令也没有按键时为空', content.irQuick(empty).length === 0);
push('limit 生效', content.irQuick(tv, 2).length === 2);

// ---- 副标题：写品类与键数，不写「状态未知」 ----
push('电视遥控副标题带键数', content.irSubText(tv) === '电视遥控 · 3 键');
push('没有按键时不带尾巴', content.irSubText(empty) === '自定义遥控');

const opt = { live: {}, history: {}, names: {}, metrics: [], sizes: {}, homesCount: 1 };
const tvCard = content.buildCard(tv, opt);
push('卡片副标题用红外文案', tvCard.subText === '电视遥控 · 3 键');
push('副标题不是状态（不画状态点）', tvCard.subIsStatus === false);
push('卡片带 4 个红外按钮', tvCard.ir.length === 4);
push('卡片不出电源开关', tvCard.showSwitch === false && tvCard.switches.length === 0);
push('有按钮的卡片不算空壳', tvCard.bare === false);
push('卡片不出枚举 chips（红外没有可写枚举）', tvCard.chips.length === 0);
const acCard = content.buildCard(ac, opt);
push('空调遥控卡片按钮只摆命令（温度不在命令表里）',
  acCard.ir.map((c) => c.label).join() === '开机,制冷');
push('温度不占卡片按钮位（步进在详情里）',
  acCard.ir.every((c) => String(c.label).indexOf('°C') < 0));
const emptyCard = content.buildCard(empty, opt);
push('空遥控器收成单格且没有按钮', emptyCard.ir.length === 0 && emptyCard.size === 'sm');
const offCard = content.buildCard(offTv, opt);
push('离线红外卡片不摆按钮、副标题回到「离线」',
  offCard.ir.length === 0 && offCard.subText === '离线');
push('离线也不给开关', offCard.showSwitch === false);
push('cardHasContent 认红外按钮', content.cardHasContent(tv, {}) === true
  && content.cardHasContent(empty, {}) === false);

// 小卡不摆按钮（寸土寸金，交给详情）
const smCard = content.buildCard(tv, Object.assign({}, opt, { sizes: { 'ir.1': 'sm' } }));
push('小卡不渲染红外按钮', smCard.ir.length === 0);
const lgCard = content.buildCard(tv, Object.assign({}, opt, { sizes: { 'ir.1': 'lg' } }));
push('大卡摆满命令表（上限 6 个）', lgCard.ir.length === TV_CMDS.length);

// ---- 图标：14 类，ir 有专属图形，与旧版逐字一致 ----
push('图标覆盖 14 个类别', icons.CATS.length === 14);
push('CATS 与旧版一致', eq(oldIcons.CATS, icons.CATS));
push('ir 有专属图标', icons.has('ir'));
push('ir 图标与旧版逐字一致', oldIcons.svg('ir') === icons.svg('ir'));
push('PATHS 与旧版逐字一致', eq(oldIcons.PATHS, icons.PATHS));
push('ir 图标不写死颜色', !/stroke="#|fill="#/.test(icons.svg('ir')));

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
            payload = json.loads(line)
    ok(payload.get("fail") == [], "Node 运行时校验 %s 项全过" % payload.get("total", 0))
    ok_n[0] += int(payload.get("total", 0))

# ---- 静态接线 ----
card_vue = read(path(SRC, "components", "DeviceCard.vue"))
ok("model.ir.length" in card_vue, "卡片渲染红外按钮")
ok("store.pressIr(" in card_vue, "卡片按钮走 pressIr（按命令/按键分流）")
ok("chip ir-chip" in card_vue, "红外按钮复用 chip 外观并带专属类")
ok("active" not in card_vue.split("dc-ir")[1].split("</div>")[0],
   "红外按钮不做选中态（没有状态可表达）")

panel = read(path(SRC, "components", "IrPanel.vue"))
ok("props.ir.cmds" in panel or "ir.cmds" in panel, "面板按命令表分组")
ok("dense" in panel, "模式用密集网格")
ok("这台遥控器在米家侧还没有可用的按键" in panel,
   "空遥控器如实说明，而不是摆一堆点不动的空按钮")
ok("offline" in panel, "离线时禁用按钮并解释原因")
# 温度：－ 26°C ＋ 步进，不是一排 °C 按钮
ok("ir-temp-v" in panel and "ir-step" in panel, "温度渲染成「－ 26°C ＋」步进")
ok("store.setIrTemp(" in panel, "温度走 setIrTemp（绝对值下发）")
ok("localStorage" in panel, "温度本机记住（云端只写不读）")
ok("TEMP_AFTER" in panel, "温度块插在模式/电源之后（和实体遥控器键位一致）")
ok("本机记录" in panel, "温度旁标出「本机记录」，不冒充云端状态")

store_src = read(path(SRC, "stores", "devices.ts"))
ok("'/api/ir/press'" in store_src and "'/api/ir/cmd'" in store_src,
   "两条接口都在数据层")
ok("已发送：" in store_src, "下发成功给明确回执（红外没有状态可回读）")
ok("红外是单向发码" in store_src, "数据层注释写明不做乐观更新")
ok("if (d && d.online === false) { toast('设备离线，指令发不出去')" in store_src,
   "离线先拦，不发无效请求")

ins = read(path(SRC, "styles", "components.css"))
ok(".ir-keys" in ins and ".ir-btns.dense" in ins, "遥控面板样式齐全")
ok("grid-auto-rows" in ins, "按键网格行高固定，滚动不截半个字")
ok(".chip.ir-chip:active" in ins, "按下有反馈但不留选中态")

# 旧界面同步：分类与图标必须一致，否则回退后红外会掉回「网关」
legacy_cards = read(path(ROOT, "static", "cards.js"))
ok("ir: \"红外遥控\"" in legacy_cards, "旧界面分类表同步新增 ir")
ok("[/^miir\\.|^ir\\.|红外遥控/, \"ir\"]" in legacy_cards, "旧界面分类规则同步")
ok("blk.cmds" in legacy_cards, "旧界面尺寸判定同步认命令表")
legacy_types = read(path(ROOT, "static", "card_types.js"))
ok('"ir"' in legacy_types, "旧界面注册了 ir 渲染器（缺了会让红外卡片渲染不出来）")

print("\n通过 %d 项" % ok_n[0])
