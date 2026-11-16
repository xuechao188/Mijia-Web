#!/usr/bin/env python3
"""红外遥控（虚拟设备）能力与接口不变量。

背景：米家的红外遥控没有 on 属性，控制面在**动作**（turn-on / 音量±）与
**云端按键表**（自定义遥控）上。以前只认「on 属性 + 属性白名单 + 摄像头动作」，
于是 8 台红外设备全部退化成"能看见、点不动"。本测试盯住五件事：

1) 识别：did=ir.* / model=miir.*，别把普通设备误判进来
2) 命令表：动作顺序（开机在关机前）、带参动作过滤、模式/设定温度的取值、
   有「设定温度」时不再摆相对的「温度 ±」
3) 按键表：磁盘缓存往返、TTL、解析、预取单飞
4) 视图：cap.on=False（绝不伪造开关）、product 用中文品类、动作照收
5) 接口：越权 key_id / 越权 cmd_id / 非红外设备一律拒绝
"""
import json
import os
import sys
import tempfile
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "web", "src")
sys.path.insert(0, ROOT)

tmp = tempfile.mkdtemp(prefix="mijia-ir-")
os.environ["MIHOME_DATA_DIR"] = tmp

import app as appmod            # noqa: E402
import config                   # noqa: E402
from services import cloud      # noqa: E402
from services import devices as dev  # noqa: E402
from services import ir         # noqa: E402
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


def spec_of(services):
    return {"services": services}


# ---------------------------------------------------------------- 1. 识别
ok(ir.is_ir({"did": "ir.123", "model": "x"}), "did 以 ir. 开头判为红外")
ok(ir.is_ir({"did": "123", "model": "miir.tv.ir01"}), "model 以 miir. 开头判为红外")
ok(not ir.is_ir({"did": "123", "model": "yeelink.light.lamp1"}),
   "普通灯具不会被误判成红外")
ok(not ir.is_ir({"did": "123", "model": "chuangmi.ir.v2"}),
   "带 ir. 片段的实体设备（chuangmi.ir.v2）不算虚拟遥控")
ok(not ir.is_ir(None), "空设备不报错、返回 False")

ok(ir.kind_of("miir.tv.ir01") == "tv", "电视遥控型号归到 tv")
ok(ir.kind_of("miir.stb.ir01") == "stb", "机顶盒遥控归到 stb")
ok(ir.kind_of("miir.aircondition.ir02") == "ac",
   "空调遥控归到 ac（aircondition 先于其它关键字）")
ok(ir.kind_of("miir.light.ir01") == "light", "灯具遥控归到 light")
ok(ir.kind_of("miir.wifispeaker.ir01") == "speaker", "音箱遥控归到 speaker")
ok(ir.kind_of("miir.remote.ir01") == "remote", "自定义遥控兜底为 remote")
ok(ir.label_of("miir.aircondition.ir02") == "空调遥控", "品类中文名：空调遥控")

# ---------------------------------------------------------------- 2. 命令表
TV = spec_of([
    {"iid": 1, "type": "urn:miot-spec-v2:service:device-information:00007801:x:1",
     "properties": [{"iid": 1, "type": "urn:miot-spec-v2:property:manufacturer:00000001:x:1",
                     "format": "string", "access": ["read"]}]},
    {"iid": 2, "type": "urn:miot-spec-v2:service:ir-tv-control:00007822:x:1",
     "actions": [
         {"iid": 5, "type": "urn:miot-spec-v2:action:volume-down:00002851:x:1", "in": []},
         {"iid": 6, "type": "urn:miot-spec-v2:action:volume-up:00002850:x:1", "in": []},
         {"iid": 1, "type": "urn:miot-spec-v2:action:turn-off:00002809:x:1", "in": []},
         {"iid": 2, "type": "urn:miot-spec-v2:action:turn-on:00002808:x:1", "in": []},
         {"iid": 3, "type": "urn:miot-spec-v2:action:set-channel-number:00002860:x:1",
          "in": [{"piid": 1}]},
     ]},
])
cmds = ir.build_cmds(TV)
labels = [c["label"] for c in cmds]
ok(labels[0] == "开机" and labels[1] == "关机",
   "电源组固定「开机 → 关机」，即便 spec 里 turn-off 的 aiid 更小")
ok(labels.index("音量 ＋") < labels.index("音量 －"),
   "同组内 ＋ 排在 － 前面（spec 里 volume-down 的 iid 更小）")
ok("设置频道号" not in labels and all(c["name"] != "set-channel-number" for c in cmds),
   "需要入参的动作不进按钮列表（没有输入框，点了必然失败）")
ok(len(cmds) == 4, "其余动作数量正确（4 个无参动作）")
ok(all(c["kind"] == "action" and c["siid"] == 2 for c in cmds), "动作命令带 siid/aiid 与 kind=action")

AC = spec_of([
    {"iid": 2, "type": "urn:miot-spec-v2:service:ir-aircondition-control:00007824:x:1",
     "properties": [
         {"iid": 1, "type": "urn:miot-spec-v2:property:ir-mode:0000004C:x:1",
          "format": "uint8", "access": ["write"],
          "value-list": [{"value": 0, "description": "Auto"},
                         {"value": 1, "description": "Cool"},
                         {"value": 2, "description": "Dry"},
                         {"value": 3, "description": "Heat"},
                         {"value": 4, "description": "Fan"}]},
         {"iid": 2, "type": "urn:miot-spec-v2:property:ir-temperature:0000004D:x:1",
          "format": "float", "access": ["write"], "unit": "celsius",
          "value-range": [16, 30, 1]},
         {"iid": 3, "type": "urn:miot-spec-v2:property:volume-increase:00002860:x:1",
          "format": "uint8", "access": ["write"]},
     ],
     "actions": [
         {"iid": 5, "type": "urn:miot-spec-v2:action:turn-off:00002809:x:1", "in": []},
         {"iid": 6, "type": "urn:miot-spec-v2:action:turn-on:00002808:x:1", "in": []},
         {"iid": 3, "type": "urn:miot-spec-v2:action:temperature-down:0000281E:x:1", "in": []},
         {"iid": 4, "type": "urn:miot-spec-v2:action:temperature-up:0000281D:x:1", "in": []},
         {"iid": 1, "type": "urn:miot-spec-v2:action:fan-speed-down:0000281C:x:1", "in": []},
         {"iid": 2, "type": "urn:miot-spec-v2:action:fan-speed-up:0000281B:x:1", "in": []},
     ]},
])
ac = ir.build_cmds(AC)
modes = [c for c in ac if c["group"] == "模式"]
ok([m["label"] for m in modes] == ["自动", "制冷", "除湿", "制热", "送风"],
   "模式按 spec 取值顺序铺，且翻成中文")
ok(all(m["kind"] == "set" and m["value"] is not None for m in modes),
   "模式是 set 命令（ir-mode 只写属性），带下发值")
temps = [c for c in ac if c["group"] in ("设定温度", "温度")]
ok(temps == [], "温度不进命令表：它是一条「－ 26°C ＋」步进，不是十几个按钮")
ok(not [c for c in ac if c.get("prop") == "volume-increase"],
   "volume-increase 这类「步长」属性不做成按钮（点一下发多少不确定）")
ok([c["label"] for c in ac if c["group"] == "电源"] == ["开机", "关机"], "空调电源顺序正确")
ok([c["group"] for c in ac][:2] == ["电源", "电源"], "电源组永远排第一")
ok(ir.build_cmds({}) == [], "没有 spec 时命令表为空")
ok(ir.build_cmds(None) == [], "spec 为 None 时不抛错")

# 温度步进：量程 / 步长 / 默认值
AC_TEMP = ir.build_temp(AC)
ok(AC_TEMP == {"siid": 2, "piid": 2, "min": 16, "max": 30, "step": 1, "default": 26},
   "ir-temperature 解析成步进定义（16–30°C，默认 26°C）")
ok(ir.build_temp(TV) is None, "电视遥控没有温度控制")
ok(ir.build_temp(None) is None, "没有 spec 时不抛错")

# 量程异常（过宽）不给温度控件
FAKE_RANGE = spec_of([{"iid": 2, "type": "urn:miot-spec-v2:service:s:00007824:x:1",
                       "properties": [{"iid": 1,
                                       "type": "urn:miot-spec-v2:property:ir-temperature:0000004D:x:1",
                                       "format": "float", "access": ["write"],
                                       "value-range": [0, 300, 1]}]}])
ok(ir.build_temp(FAKE_RANGE) is None, "量程过宽（300 档）不给温度控件")
ok(ir.build_cmds(FAKE_RANGE) == [], "量程异常时也不摆相对的「温度 ±」")

# 校验：越界、非整数、非步长一律拒绝
ok(ir.temp_ok(AC_TEMP, 26), "量程内的整数温度通过")
ok(ir.temp_ok(AC_TEMP, "28"), "字符串数字也认（前端 JSON 可能带引号）")
ok(not ir.temp_ok(AC_TEMP, 15) and not ir.temp_ok(AC_TEMP, 31), "越界温度拒绝")
ok(not ir.temp_ok(AC_TEMP, 26.4), "非整数温度拒绝")
ok(not ir.temp_ok(AC_TEMP, "abc") and not ir.temp_ok(AC_TEMP, None), "非法值拒绝")
ok(not ir.temp_ok(None, 26), "没有温度控件时一律拒绝")
HALF = dict(AC_TEMP, step=2)
ok(ir.temp_ok(HALF, 26) and not ir.temp_ok(HALF, 27), "步长 2°C 时奇数温度拒绝")

# ---------------------------------------------------------------- 3. 按键表缓存
DID = "ir.100"
ir._KEYS.clear()
ir._KEYS_AT.clear()
ok(ir.keys(DID) == [], "没有缓存时返回空表而不是报错")
ok(ir.is_stale(DID), "没有缓存视为过期")
ir._KEYS[DID] = [{"id": 1, "name": "电源"}]
ir._KEYS_AT[DID] = time.time()
ir._save_disk()
saved = json.loads(read(config.IR_KEYS_PATH))
ok(saved[DID]["keys"][0]["name"] == "电源", "按键表落盘（did → keys）")
ir._KEYS.clear()
ir._KEYS_AT.clear()
ir._disk_loaded = False
ok(ir.keys(DID) == [{"id": 1, "name": "电源"}], "重启后从磁盘恢复按键表")
ok(not ir.is_stale(DID), "刚写过的缓存不算过期")
ir._KEYS_AT[DID] = time.time() - config.IR_KEYS_TTL_S - 1
ok(ir.is_stale(DID), "超过 TTL 视为过期")


class FakeService:
    """miio_request 的最小替身：按键表与发码都记下来。"""

    def __init__(self, keys_payload):
        self.keys_payload = keys_payload
        self.calls = []

    async def miio_request(self, path, params):
        self.calls.append((path, dict(params or {})))
        return {"keys": self.keys_payload}


fake = FakeService([
    {"id": 100000001, "name": "POWER", "display_name": "电源"},
    {"id": 100000002, "name": "PAUSE"},
    {"no_id": True},
])
S["service"] = fake
S["logged_in"] = True
ir._KEYS.pop(DID, None)
ir._KEYS_AT.pop(DID, None)
res = ir.refresh(DID)
ok(len(res) == 2, "解析按键表时丢掉没有 id 的脏数据")
ok(res[0]["name"] == "电源", "优先用 display_name（中文）当按键名")
ok(res[1]["name"] == "暂停" or res[1]["name"] == "PAUSE", "没有 display_name 时退回 name")
ok(fake.calls and fake.calls[-1][0] == "/v2/irdevice/controller/keys",
   "按键表走 /v2/irdevice/controller/keys")

fake.calls.clear()
ir.press(DID, 100000002)
ok(fake.calls[-1] == ("/v2/irdevice/controller/key/click",
                      {"did": DID, "key_id": 100000002}),
   "按键发码走 key/click，key_id 转成整数")

# 预取：单飞，同一批设备不会起两条线程
started = []
_real_thread = ir.threading.Thread


class FakeThread:
    def __init__(self, target=None, daemon=None, name=None):
        self.target = target

    def start(self):
        started.append(1)


ir.threading.Thread = FakeThread
try:
    ir._KEYS_AT[DID] = 0
    n1 = ir.prefetch([DID])
    n2 = ir.prefetch([DID])
finally:
    ir.threading.Thread = _real_thread
    ir._prefetching = False
ok(n1 == 1, "预取把过期设备排进队列")
ok(len(started) == 1, "预取只起一条后台线程")
ok(n2 in (0, 1), "重复调用不会重复排（单飞或已入队）")
ok(ir.prefetch([]) == 0, "空列表不做事")

# ---------------------------------------------------------------- 4. 设备视图
S["service"] = object()
S["logged_in"] = True
ir._KEYS[DID] = [{"id": 7, "name": "上升"}]
ir._KEYS_AT[DID] = time.time()

v = dev.build_device_view({"did": "ir.9", "name": "床", "model": "miir.remote.ir01",
                           "isOnline": True}, {})
ok(v["ir"] is not None and v["ir"]["kind"] == "remote", "自定义遥控在视图里带 ir 块")
ok(v["cap"]["on"] is False, "红外不伪造电源能力（cap.on=False）")
ok(v["switches"] == [], "红外不产生开关位（否则卡片会长出一个点了没用的开关）")
ok(v["product"] == "自定义遥控", "product 用中文品类，不露 miir.* 型号")
ok(v["on_guess"] is False, "红外是「确认无能力」，不是猜测态")

v2 = dev.build_device_view({"did": "ir.8", "name": "电视遥控", "model": "miir.tv.ir01",
                            "isOnline": True}, TV)
ok(len(v2["ir"]["cmds"]) == 4, "有 spec 时视图带命令表")
ok(len(v2["actions"]) == 5, "spec 动作照收（/api/camera/action 仍可校验）")
ok(v2["ir"]["note"], "红外带「单向发码」说明，界面不用另写文案")
ok(v2["ir"]["temp"] is None, "电视遥控的温度位为空，界面不会画步进")

v3 = dev.build_device_view({"did": "ir.6", "name": "空调遥控",
                            "model": "miir.aircondition.ir02", "isOnline": True}, AC)
ok(v3["ir"]["temp"] == {"siid": 2, "piid": 2, "min": 16, "max": 30, "step": 1, "default": 26},
   "空调视图带温度步进（16–30°C，默认 26）")
ok(not [c for c in v3["ir"]["cmds"] if c["group"] == "设定温度"],
   "视图命令表里不再有 16 个 °C 按钮")

empty = dev.build_device_view({"did": "ir.7", "name": "空遥控", "model": "miir.remote.ir01",
                               "isOnline": True}, {})
ok(empty["ir"]["note"] == "", "一个键都没配时不摆「单向发码」说明（没东西可发）")

# ---------------------------------------------------------------- 5. 接口
S["views"] = {"ir.8": v2, "ir.9": v, "ir.6": v3, "cam1": {"did": "cam1", "name": "摄像头"}}

calls = []
ir.press = lambda did, kid: calls.append(("press", did, kid))
ir.run_cmd = lambda did, cmd: calls.append(("cmd", did, cmd.get("label")))
ir.set_temp = lambda did, value: calls.append(("temp", did, value))
ir._KEYS["ir.9"] = [{"id": 7, "name": "上升"}]
v["ir"]["keys"] = [{"id": 7, "name": "上升"}]

c = appmod.create_app().test_client()
r = c.get("/api/ir/keys?did=ir.9")
ok(r.status_code == 200 and r.get_json()["keys"][0]["name"] == "上升",
   "GET /api/ir/keys 返回按键表")
ok(c.get("/api/ir/keys?did=cam1").status_code == 404, "非红外设备查按键表返回 404")

r = c.post("/api/ir/press", json={"did": "ir.9", "key_id": 7})
ok(r.status_code == 200 and r.get_json()["ok"], "POST /api/ir/press 正常发码")
r = c.post("/api/ir/press", json={"did": "ir.9", "key_id": 999})
ok(r.status_code == 400 and "拒绝" in r.get_json()["error"],
   "key_id 不在按键表里一律拒绝（防越权）")
r = c.post("/api/ir/press", json={"did": "ir.9"})
ok(r.status_code == 400, "缺 key_id 返回 400")

cmd_id = v2["ir"]["cmds"][0]["id"]
r = c.post("/api/ir/cmd", json={"did": "ir.8", "cmd_id": cmd_id})
ok(r.status_code == 200 and r.get_json()["label"] == "开机", "POST /api/ir/cmd 下发命令")
r = c.post("/api/ir/cmd", json={"did": "ir.8", "cmd_id": "a:9:9"})
ok(r.status_code == 400 and "拒绝" in r.get_json()["error"],
   "不在命令表里的 cmd_id 一律拒绝")
r = c.post("/api/ir/cmd", json={"did": "cam1", "cmd_id": cmd_id})
ok(r.status_code == 404, "对非红外设备下发命令返回 404")
r = c.post("/api/ir/cmd", json={"did": "ir.8"})
ok(r.status_code == 400, "缺 cmd_id 返回 400")
ok(("cmd", "ir.8", "开机") in calls and ("press", "ir.9", 7) in calls,
   "两条通道都真的调到了发码/命令层")

# 温度：只收绝对值，越界/非温度设备一律拒绝
r = c.post("/api/ir/temp", json={"did": "ir.6", "value": 27})
ok(r.status_code == 200 and r.get_json()["label"] == "27°C", "POST /api/ir/temp 下发绝对温度")
r = c.post("/api/ir/temp", json={"did": "ir.6", "value": 30})
ok(r.status_code == 200 and ("temp", "ir.6", 30) in calls, "边界值（上限）可以下发")
r = c.post("/api/ir/temp", json={"did": "ir.6", "value": 31})
ok(r.status_code == 400 and "16–30" in r.get_json()["error"], "超上限返回 400 并说明量程")
r = c.post("/api/ir/temp", json={"did": "ir.6", "value": 25.5})
ok(r.status_code == 400, "非整数温度拒绝")
r = c.post("/api/ir/temp", json={"did": "ir.8", "value": 26})
ok(r.status_code == 400 and "没有温度控制" in r.get_json()["error"],
   "电视遥控没有温度控制，返回 400")
r = c.post("/api/ir/temp", json={"did": "cam1", "value": 26})
ok(r.status_code == 404, "非红外设备设定温度返回 404")
r = c.post("/api/ir/temp", json={"did": "ir.6"})
ok(r.status_code == 400, "缺 value 返回 400")
ok(("temp", "ir.6", 27) in calls, "温度真的调到了属性下发层")

# 失败要带可读提示，不能把云端原文直接甩给用户
def boom(did, cmd):
    raise RuntimeError("code=-127 client withdraw")


ir.run_cmd = boom
r = c.post("/api/ir/cmd", json={"did": "ir.8", "cmd_id": cmd_id})
ok(r.status_code == 502 and r.get_json()["hint"],
   "下发失败返回 502 且带 hint（前端直接展示）")

# ---------------------------------------------------------------- 6. 轮询不读红外
from services import live as livemod   # noqa: E402

plan = livemod.build_read_plan(S["views"])
ok(not [p for p in plan if str(p[0]).startswith("ir.")],
   "3 秒快轮询不为红外设备生成读参数（它没有可读状态）")

# ---------------------------------------------------------------- 7. 前端接线
types = read(os.path.join(SRC, "devices", "types.ts"))
ok("IrInfo" in types and "IrCmd" in types and "'ir'" in types, "类型层有 ir 类别与 ir 块")
ok("interface IrTemp" in types and "temp?: IrTemp" in types, "类型层有温度步进定义")
cards_ts = read(os.path.join(SRC, "devices", "cards.ts"))
ok("红外遥控" in cards_ts and "irActionCount" in cards_ts, "分类层有红外标签与按钮计数")
ok("/^miir\\.|^ir\\.|红外遥控/" in cards_ts,
   "分类规则把红外排在第一位（否则被 light / aircondition 抢走）")
panel = read(os.path.join(SRC, "components", "IrPanel.vue"))
ok("单向发码" in panel or "ir.note" in panel, "详情面板有遥控块与说明")
ok("pressIrKey" in panel and "pressIr(" in panel, "面板点按分别接按键与命令")
ok("setIrTemp" in panel and "ir-temp" in panel, "空调温度是「－ 26°C ＋」步进，不走命令按钮")
ok("localStorage" in panel, "温度值本机记住（云端读不回，只能记最后一次发送）")
drawer = read(os.path.join(SRC, "components", "DeviceDrawer.vue"))
ok("<IrPanel" in drawer, "设备详情挂上了遥控面板")
ok("if (d.value.ir) return ''" in drawer, "红外不重复显示产品名那一行")
store = read(os.path.join(SRC, "stores", "devices.ts"))
ok("'/api/ir/press'" in store and "'/api/ir/cmd'" in store, "前端分别接两条接口")
ok("'/api/ir/temp'" in store and "setIrTemp" in store, "前端接温度接口")
ok("ensureIrKeys" in store, "启动与开抽屉时补齐按键表")
css = read(os.path.join(ROOT, "web", "src", "styles", "components.css"))
ok(".ir-keys" in css and "grid-auto-rows" in css,
   "按键网格写死行高，滚动区不会在半个字上截断")
ok(".ir-temp" in css and ".ir-step" in css, "温度步进有独立样式（圆角方键 + 居中数值）")

print("\nir_test: %d 项通过" % ok_n[0])
