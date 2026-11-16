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
ok("isFresh(n)" in store, "只有新到的才弹，补跑的历史不连环震")
ok("NOTICE_POLL_MS = 10000" in store, "前端 10 秒轮一次本地接口")
ok("known.has(n.msg_id)" in store and "known.add(n.msg_id)" in store,
   "已提示过的 msg_id 不重复弹")
ok("devices.openDrawer(n.did)" in store, "点通知能跳到对应设备详情")

panel = read(path(SRC, "components", "NoticesPanel.vue"))
ok("store.markAll()" in panel and "store.refresh()" in panel, "面板有全部已读与立即检查")
ok("noticeTitle(n)" in panel and "noticeSub(n)" in panel, "面板逐条展示标题与设备/房间")
ok("store.perm === 'denied'" in panel, "浏览器屏蔽通知时有明确说明")

toast = read(path(SRC, "components", "NoticeToasts.vue"))
ok("store.toasts" in toast and "store.dismiss(" in toast, "卡片可关闭、随 store 收起")
ok("store.requestPerm()" in toast, "卡片里也能一键开系统通知")

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
console.log(JSON.stringify({ total: total + 3, fail: fail }));
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
       "通知纯逻辑 18 项运行期校验通过 %s" % (payload.get("fail") or ""))
    ok_n[0] += int(payload.get("total", 0))

# README 登记
readme = read(path(ROOT, "README.md"))
ok("设备通知" in readme and "test_notices.py" in readme, "README 记录设备通知与新增测试")

print("\n设备通知 %d 项通过" % ok_n[0])
