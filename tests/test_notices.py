#!/usr/bin/env python3
"""设备通知（米家消息中心）不变量。

1) 同步语义：首次把现存未读当历史、新消息才提醒、按 msg_id 去重、
   云端不再列出就算在别处读过；全程不写云端已读态。
2) 接口形状：/api/notices、/read、/refresh。
3) 前端接线：通知标签在日志前、未读角标、右下角卡片、系统通知与权限、
   写模式后回读亮度/色温（灯具联动）。
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "web", "src")
sys.path.insert(0, ROOT)

tmp = tempfile.mkdtemp(prefix="mijia-notice-")
os.environ["MIHOME_DATA_DIR"] = tmp

import app as appmod            # noqa: E402
import config                   # noqa: E402
from services import cloud      # noqa: E402
from services import notices    # noqa: E402
from services.state import S    # noqa: E402

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


# ---------------------------------------------------------------- 云端打桩
MSGS = [
    {"msg_id": 1001, "type": 6, "title": "有人按门铃", "content": "鹿客一握开智能锁",
     "did": "1193921595", "ctime": 1794798719, "is_new": 1,
     "params": {"body": {"event": "5.1006", "model": "loock.lock.416",
                         "homeRoomExtra": {"homeName": "信地", "roomName": "门厅"}}}},
    {"msg_id": 1002, "type": 13, "title": "无人存在-关灯 09:59 执行成功",
     "content": "", "did": "", "ctime": 1794794386, "is_new": 1, "params": {}},
]
PAYLOAD = {"messages": list(MSGS)}


class FakeService:
    def miio_request(self, uri, data):
        assert uri == "/v2/message/v2/typelist", uri
        return PAYLOAD


def fake_call(coro, timeout=None, what=""):
    return PAYLOAD


cloud.call = fake_call
S["service"] = FakeService()
S["logged_in"] = True

# ---------------------------------------------------------------- 1. 同步语义
first = notices.sync()
ok(first == [], "首次同步不把现存未读当成新通知（当历史）")
rows = notices.recent(10)
ok(len(rows) == 2, "两条消息都已落盘（列表里看得到）")
ok(all(r["seen"] == 1 for r in rows), "首次同步的行标记为已读，不亮红点")
ok(notices.unread() == 0, "首次同步后未读数为 0")

PAYLOAD["messages"] = list(MSGS) + [{
    "msg_id": 1003, "type": 6, "title": "清扫已完成", "content": "友望扫地机器人U400",
    "did": "1191219437", "ctime": 1794802000, "is_new": 1,
    "params": {"body": {"event": "3.2", "model": "jdyw.vacuum.u400",
                        "homeRoomExtra": {"homeName": "西山银杏", "roomName": "卫生间"}}},
}]
fresh = notices.sync()
ok(len(fresh) == 1 and fresh[0]["msg_id"] == 1003, "新到的消息才算新通知")
ok(fresh[0]["seen"] == 0 and notices.unread() == 1, "新通知未读，角标 +1")
ok(fresh[0]["room"] == "卫生间" and fresh[0]["model"] == "jdyw.vacuum.u400",
   "房间与型号从 params.body 取到")

ok(notices.sync() == [] and notices.unread() == 1, "同一条消息重复拉取不会重复计数")
ok(len(notices.recent(10)) == 3, "去重靠 msg_id，不靠标题")

PAYLOAD["messages"] = [MSGS[0]]
notices.sync()
ok(notices.unread() == 0, "云端不再列出的，视为在手机上读过了，本地跟着清")

# 归一化：字段缺失/类型异常都不该让界面拿到 None
n = notices._normalize({"msg_id": "9", "type": None, "title": None, "ctime": None})
ok(n["msg_id"] == 9 and n["kind"] == 0 and n["title"] == "" and n["ts"] == 0.0,
   "缺字段的消息归一化成空串/0，不抛异常")
n2 = notices._normalize({"msg_id": "abc"})
ok(n2["msg_id"] == 0, "msg_id 非法时归零，落盘前被过滤")

# ---------------------------------------------------------------- 2. 接口
fa = appmod.create_app()
fa.config["TESTING"] = True
c = fa.test_client()

PAYLOAD["messages"] = list(MSGS) + [{
    "msg_id": 1004, "type": 6, "title": "电池电量低，请及时更换电池！",
    "content": "水泵开关", "did": "blt.3.1l2k5s77kk800", "ctime": 1794803000,
    "is_new": 1, "params": {"body": {"event": "3.1001",
                                     "homeRoomExtra": {"homeName": "西山银杏"}}},
}]
r = c.get("/api/notices?limit=5")
d = json.loads(r.data)
ok(r.status_code == 200 and d["ok"], "GET /api/notices 可用")
ok(isinstance(d["notices"], list) and len(d["notices"]) <= 5, "limit 生效")
ok(set(["msg_id", "ts", "time", "kind", "title", "body", "did", "room", "seen"])
   <= set(d["notices"][0].keys()), "列表字段齐全（含 seen 与格式化时间）")
ok(d["unread"] >= 0 and "last_sync" in d and "error" in d, "快照带未读数与同步状态")

r = c.post("/api/notices/read", json={"ids": [1004]})
d = json.loads(r.data)
ok(d["ok"] and d["unread"] == 0, "按 msg_id 标记已读")

r = c.post("/api/notices/read", json={})
d = json.loads(r.data)
ok(d["ok"] and d["unread"] == 0, "不带 ids = 全部已读")

r = c.post("/api/notices/refresh", json={})
d = json.loads(r.data)
ok(d["ok"] and "new" in d, "POST /api/notices/refresh 立刻检查一次")

r = c.post("/api/notices/diag", json={"time": "t", "permission": "granted",
                                      "verdict": "ok", "ua": "x" * 500})
d = json.loads(r.data)
ok(r.status_code == 200 and d["ok"], "POST /api/notices/diag 记录浏览器诊断")

# ---------------------------------------------------------------- 3. 后端不变量
src = read(path(ROOT, "services", "notices.py"))
ok("/v2/message/v2/typelist" in src, "用米家消息中心的 typelist 接口拉未读")
ok("v2/message/v2/read" not in src and "markread" not in src.lower(),
   "不回写云端已读态（不替用户在手机上清红点）")
ok("msg_id INTEGER PRIMARY KEY" in src, "按 msg_id 主键去重")
ok("1 if first else 0" in src, "首次同步标记为历史")
ok(config.NOTICE_POLL_S >= 8, "通知轮询间隔不短于 8 秒，避免撞风控")
ok("cloud.cooling() > 0" in src, "风控冷却期内跳过，不硬撞 -127")

app_src = read(path(ROOT, "app.py"))
ok("notices_bp" in app_src and "notices.start()" in app_src,
   "通知蓝图注册、后台轮询随主进程启动")

live_src = read(path(ROOT, "routes", "live.py"))
ok('request.args.get("did")' in live_src, "/api/live 支持单台回读（?did=）")

# ---------------------------------------------------------------- 4. 前端接线
app_vue = read(path(SRC, "App.vue"))
ok("['notices', '通知']" in app_vue, "顶部标签新增「通知」")
ok(app_vue.find("'notices'") < app_vue.find("'logs'"), "通知排在日志前面")
ok("tab-badge" in app_vue and "notices.hasUnread" in app_vue, "未读数贴在标签上")
ok("<NoticesPanel" in app_vue and "key=\"notices\"" in app_vue, "通知面板接入主壳")
ok("<NoticeToasts />" in app_vue, "右下角通知卡接入主壳")
ok("notices.startPolling()" in app_vue and "notices.stopPolling()" in app_vue,
   "登录后开始轮询、退出即停")

store = read(path(SRC, "stores", "notices.ts"))
ok("Notification.permission" in store and "Notification.requestPermission" in store,
   "读权限、按需申请权限（必须由用户手势触发）")
ok("new Notification(" in store and "'mi-notice-'" in store, "推系统级通知并带 tag 去重")
# Edge 静默拒绝修复：granted/default/denied 三种结果都要给反馈，不能只在允许时提示
ok("isSecureContext" in store, "非安全上下文先拦截并说明原因")
seg_req = store.split("async function requestPerm")[1].split("async function openToast")[0]
for result, toast in [("granted", "NOTICE_PERM_TOAST_OK"),
                      ("default", "NOTICE_PERM_TOAST_DEFAULT"),
                      ("else", "NOTICE_PERM_ASK_DENIED")]:
    ok(toast in seg_req, "权限结果 %s 有明确反馈" % result)
ok("permAsked.value = true" in seg_req, "点过开启后标记，便于显示引导文案")
ok("await Notification.requestPermission()" in seg_req and seg_req.find("isSecureContext") < seg_req.find("await Notification.requestPermission()"),
   "requestPermission 保持在用户手势同步栈，前面不插 await")
ok("isFresh(n)" in store, "只有新到的才弹，补跑的历史不连环震")
ok("NOTICE_POLL_MS = 10000" in store, "前端 10 秒轮一次本地接口")
ok("known.has(n.msg_id)" in store and "known.add(n.msg_id)" in store,
   "已提示过的 msg_id 不重复弹")
ok("devices.openDrawer(n.did)" in store, "点通知能跳到对应设备详情")

panel = read(path(SRC, "components", "NoticesPanel.vue"))
ok("store.markAll()" in panel and "store.refresh()" in panel, "面板有全部已读与立即检查")
ok("noticeTitle(n)" in panel and "noticeSub(n)" in panel, "面板逐条展示标题与设备/房间")
ok("store.perm === 'denied'" in panel, "浏览器屏蔽通知时有明确说明")
ok("NOTICE_PERM_ASK_DEFAULT" in panel and "store.permAsked" in panel,
   "点过开启仍 default 时显示 Edge 手动开启引导")

toast = read(path(SRC, "components", "NoticeToasts.vue"))
ok("store.toasts" in toast and "store.dismiss(" in toast, "卡片可关闭、随 store 收起")
ok("store.requestPerm()" in toast, "卡片里也能一键开系统通知")

# 类型标签筛选：纯逻辑在 panels/notices.ts，UI 在 NoticesPanel.vue
ok("NOTICE_FILTERS" in panel and "activeFilter" in panel and "visible" in panel,
   "面板有类型标签与筛选后列表")
ok(':class="{ active: activeFilter === f.key }"' in panel,
   "标签单选高亮当前类型")
ok("v-for=\"n in visible\"" in panel and "counts[f.key]" in panel,
   "列表用筛选结果、标签显示各类条数")
ok("noticeCounts" in panel and "filterNotices" in panel,
   "计数与筛选复用 panels 纯逻辑")
css = read(path(SRC, "styles", "layout.css"))
ok(".nt-filter" in css and ".nt-filter .chip" in css, "标签栏样式复用 chip")

# 测试通知 + 诊断日志
ok("store.runTest()" in panel and "store.diagBusy" in panel, "面板有测试通知按钮与忙碌态")
ok("store.diag" in panel and "formatDiag(store.diag)" in panel, "面板展示诊断结论与可复制详情")
ok("async function runTest" in store and "/api/notices/diag" in store,
   "store 采集诊断并上报后端日志")
ok("runNotifyDiagnostic" in store, "store 调用浏览器环境诊断")
diag_src = read(path(SRC, "panels", "notices.ts"))
ok("export async function runNotifyDiagnostic" in diag_src, "纯逻辑提供诊断采集函数")
ok("isSecureContext" in diag_src and "navigator.permissions" in diag_src,
   "诊断覆盖安全上下文与真实权限状态")
ok("new Notification(" in diag_src and "testSent" in diag_src,
   "诊断实际尝试发送并记录结果")
ok("export function formatDiag" in diag_src, "诊断可格式化为可复制文字")
routes_src = read(path(ROOT, "routes", "notices.py"))
ok('"/api/notices/diag"' in routes_src and "log.info" in routes_src,
   "后端 diag 接口把诊断写入日志")

# 灯具切模式后会连带改亮度/色温：写完必须回读
drawer = read(path(SRC, "components", "DeviceDrawer.vue"))
ok("async function pickEnum" in drawer and "store.settleDevice(did.value)" in drawer,
   "枚举（模式）写成功后触发一次回读")
ok("rangeVals.value = {}" in drawer, "回读前清掉滑块临时值，否则显示的是旧值")
ok("store.refreshDevice(did.value)" in drawer, "拉杆松手后也回读一次，拿设备夹过的真值")

dev_ts = read(path(SRC, "stores", "devices.ts"))
ok("async function refreshDevice" in dev_ts and "/api/live?did=" in dev_ts,
   "单台回读走 /api/live?did=")
ok(dev_ts.count("await refreshDevice(did)") == 2, "settleDevice 回读两拍（先模式、后联动）")
ok("Promise<boolean>" in dev_ts.split("async function setControl")[1][:200],
   "写入结果返回布尔，组件据此决定要不要回读")

css = read(path(SRC, "styles", "components.css"))
ok(".tab-badge" in css and "var(--blue)" in css.split(".tab-badge")[1].split("}")[0],
   "角标用强调色，不另起装饰色")
ok(".nt-stack" in css and "position: fixed" in css.split(".nt-stack")[1].split("}")[0],
   "卡片固定在右下角")
lay = read(path(SRC, "styles", "layout.css"))
ok(".nt-list li.is-new .nt-dot" in lay, "未读只有一个蓝点，不做整行高亮")
ok(".nt-list li.warn .nt-title" in lay, "告警类标题标红")

# ---------------------------------------------------------------- 5. 纯逻辑运行时校验
with tempfile.TemporaryDirectory(prefix="vue_notice_") as tdir:
    text = read(path(SRC, "panels", "notices.ts"))
    text = re.sub(r"from '\./types'", "from './types.ts'", text)
    open(path(tdir, "notices.ts"), "w", encoding="utf-8").write(text)
    open(path(tdir, "types.ts"), "w", encoding="utf-8").write(
        read(path(SRC, "panels", "types.ts")))
    probe = r'''
const TMP = process.argv[2];
const n = await import('file://' + TMP + '/notices.ts');
let total = 0; const fail = [];
const push = (m, c) => { total++; if (!c) fail.push(m); };
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);

push('kind6', n.noticeKind({ kind: 6 }) === '设备消息');
push('kind13', n.noticeKind({ kind: 13 }) === '智能场景');
push('kindOther', n.noticeKind({ kind: 1 }) === '系统消息');
push('titleFallback', n.noticeTitle({ kind: 6, title: '  ' }) === '设备消息');
push('titleTrim', n.noticeTitle({ kind: 6, title: ' 有人按门铃 ' }) === '有人按门铃');
push('subFull', n.noticeSub({ body: '门锁', room: '门厅', home: '信地' }) === '门锁 · 门厅 · 信地');
push('subRoom', n.noticeSub({ room: '门厅' }) === '门厅');
push('subModel', n.noticeSub({ body: '', room: '', home: '', model: 'x.y' }) === 'x.y');
push('toneWarn', n.noticeTone({ title: '电池电量低，请及时更换电池！' }) === 'warn');
push('toneOk', n.noticeTone({ title: '清扫已完成' }) === '');
push('line', n.noticeLine({ title: '有人按门铃', body: '门锁', room: '门厅' })
     === '有人按门铃｜门锁 · 门厅');
push('lineBare', n.noticeLine({ title: '清扫已完成' }) === '清扫已完成');
push('age0', n.noticeAge(1000, 1000) === '刚刚');
push('ageMin', n.noticeAge(1000, 1000 + 125) === '2 分钟前');
push('ageHour', n.noticeAge(1000, 1000 + 7200) === '');
push('freshIn', n.isFresh({ ts: 1000 }, 1000 + 60) === true);
push('freshOut', n.isFresh({ ts: 1000 }, 1000 + n.NOTICE_FRESH_S + 1) === false);
push('freshNoTs', n.isFresh({ ts: 0 }, 2000) === false);
// 类型标签筛选
const items = [{ msg_id: 1, kind: 6 }, { msg_id: 2, kind: 13 },
               { msg_id: 3, kind: 13 }, { msg_id: 4, kind: 99 }];
const cnt = n.noticeCounts(items);
push('cntAll', cnt.all === 4 && cnt.device === 1 && cnt.scene === 2 && cnt.system === 1);
push('filterAll', n.filterNotices(items, 'all').length === 4);
push('filterDevice', n.filterNotices(items, 'device').map(x => x.msg_id).join() === '1');
push('filterScene', n.filterNotices(items, 'scene').map(x => x.msg_id).join() === '2,3');
push('filterSystem', n.filterNotices(items, 'system').map(x => x.msg_id).join() === '4');
push('filterEmpty', n.filterNotices([], 'scene').length === 0);
push('tagsFour', n.NOTICE_FILTERS.length === 4 && n.NOTICE_FILTERS[0].key === 'all');
// 诊断：格式化/常量/函数存在性（构造逻辑依赖真实浏览器，另由界面实测）
const d = { time: 'T', ua: 'UA', origin: 'O', secure: true, hasApi: true,
  permission: 'granted', queryState: 'granted', testSent: true, testError: '', verdict: 'V' };
const fmt = n.formatDiag(d);
push('diagFmt', fmt.includes('权限: granted') && fmt.includes('结论: V') && fmt.includes('T'));
push('diagFn', typeof n.runNotifyDiagnostic === 'function');
push('diagConst', n.NOTICE_TEST_TITLE.includes('自检') && !!n.NOTICE_TEST_BODY);
// 诊断结论按平台给引导：Mac 不显示 Windows 步骤，反之亦然
const macUA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Edg/157.0.0.0';
const winUA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/157.0.0.0';
const vMac = n.notifyVerdict(true, true, 'granted', 'granted', true, '', macUA);
const vWin = n.notifyVerdict(true, true, 'granted', 'granted', true, '', winUA);
push('verdictMac', vMac.includes('专注模式') && vMac.includes('提醒') && !vMac.includes('Windows'));
push('verdictWin', vWin.includes('专注助手') && vWin.includes('右下角') && !vWin.includes('专注模式'));
push('verdictNoPromise', !vMac.includes('自检通知已发出'));
push('verdictDenied', n.notifyVerdict(true, true, 'denied', 'denied', false, '', macUA).includes('拒绝'));
push('verdictDefault', n.notifyVerdict(true, true, 'default', 'default', false, '', winUA).includes('静默阻尼'));
push('hintMac', n.notifyPlatformHint(macUA).includes('右上角时间'));
push('hintWin', n.notifyPlatformHint(winUA).includes('右下角通知中心'));
console.log(JSON.stringify({ total: total, fail: fail }));
'''
    p = subprocess.run(["node", "--experimental-strip-types", "--input-type=module",
                        "-e", probe, str(ROOT), tdir],
                       capture_output=True, text=True)
    if p.returncode != 0:
        print(p.stderr[-800:])
    payload = {}
    for line in p.stdout.strip().splitlines():
        if line.startswith("{"):
            payload = json.loads(line)
    ok(p.returncode == 0 and payload.get("fail") == [],
       "通知纯逻辑运行期校验通过 %s" % (payload.get("fail") or ""))
    ok_n[0] += int(payload.get("total", 0))

# README 登记
readme = read(path(ROOT, "README.md"))
ok("设备通知" in readme and "test_notices.py" in readme, "README 记录设备通知与新增测试")

print("\n设备通知 %d 项通过" % ok_n[0])
