"""spec 解析回归：URN 标准标识符、model 兜底、三态、空 spec、负缓存、读数轮询。

真实 MIoT spec 里 description 只是英文显示名（"Switch Status"），
标准标识符在 property URN 第 4 段；device_list("full") 只有 model 没有 type。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp(prefix="mijia-spec-")
os.environ["MIHOME_DATA_DIR"] = tmp

import config  # noqa: E402
import services.cloud as cloud  # noqa: E402
import services.devices as dev  # noqa: E402
from services import devcache, live  # noqa: E402
from services.state import S  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


URN = "urn:miot-spec-v2:%s:%s:00000001:vendor:1"


def prop(name, iid=1, fmt="bool", access=("read", "write"), display=None, **kw):
    p = {"iid": iid, "type": URN % ("property", name),
         "description": display or name.replace("-", " ").title(),
         "format": fmt, "access": list(access)}
    p.update(kw)
    return p


def svc(name, iid, props, display=None):
    return {"iid": iid, "type": URN % ("service", name),
            "description": display or name, "properties": props}


LIGHT_SPEC = {
    "description": "Light",
    "services": [
        svc("device-information", 1, [prop("model", 2, "string", ("read",))]),
        svc("light", 2, [
            prop("on", 1, display="Switch Status"),
            prop("brightness", 2, "uint8", ("read", "write", "notify"),
                 display="Brightness", **{"value-range": [1, 100, 1]}),
            prop("color-temperature", 10, "uint32",
                 ("read", "write", "notify"), display="Color Temperature",
                 **{"value-range": [2700, 5500, 1]}),
        ]),
        svc("indicator-light", 3, [prop("on", 1)]),
    ],
}

SENSOR_SPEC = {
    "description": "Temperature Humidity Sensor",
    "services": [
        svc("temperature-humidity-sensor", 2, [
            prop("temperature", 1, "float", ("read", "notify"),
                 display="Temperature", **{"value-range": [-30, 100, 0.1]}),
            prop("relative-humidity", 2, "float", ("read", "notify"),
                 display="Relative Humidity", **{"value-range": [0, 100, 0.1]}),
        ]),
        svc("battery", 3, [
            prop("battery-level", 1, "uint8", ("read", "notify"),
                 display="Battery Level", **{"value-range": [0, 100, 1]}),
        ]),
    ],
}

# ---------------------------------------------------------------- URN 解析
ok(dev._urn_name(URN % ("property", "color-temperature")) == "color-temperature",
   "URN 第 4 段取标准名")
ok(dev._urn_name("urn:yeelink-spec:property:brightness-delta:00000002:x:1")
   == "brightness-delta", "厂商自定义 URN 同样解析")
ok(dev._urn_name("not-an-urn") == "", "非 URN 返回空")
ok(dev._prop_name(prop("on", display="Switch Status")) == "on",
   "description 是英文显示名时仍从 URN 取到 on")
ok(dev._prop_name({"description": "brightness"}) == "brightness",
   "旧缓存/测试桩只有 description 时回退")
ok(dev._svc_type(svc("light", 2, [])) == "light", "服务类型从 URN 解析")

main_svc = svc("light", 2, [])
extra_svc = svc("indicator-light", 3, [])
ok(dev.map_live_key({}, extra_svc, prop("on")) is None,
   "附属服务 on 不映射电源")
ok(dev.map_live_key({}, main_svc, prop("on")) == "on", "主控 on 映射电源")
ok(dev.map_live_key({}, main_svc, prop("relative-humidity")) == "humidity",
   "相对湿度映射 humidity")
ok(dev.map_live_key({}, main_svc, prop("battery-level")) == "battery_level",
   "电量映射 battery_level")

# ---------------------------------------------------------------- 视图构造
v = dev.build_device_view({"did": "1", "name": "灯带",
                           "model": "yeelink.light.strip2"}, LIGHT_SPEC)
ok(v["on_guess"] is False and v["cap"]["on"] is True,
   "灯 spec 确认有电源能力")
ok(len(v["switches"]) == 1 and v["switches"][0]["siid"] == 2,
   "指示灯服务的 on 被排除，只剩主灯一路")
keys = {c["key"] for c in v["controls"]}
ok("brightness" in keys and "color-temperature" in keys,
   "自动识别出亮度与色温控件")
b = next(c for c in v["controls"] if c["key"] == "brightness")
ok(b["kind"] == "range" and (b["min"], b["max"], b["step"]) == (1, 100, 1),
   "亮度控件带上真实取值范围")
ct = next(c for c in v["controls"] if c["key"] == "color-temperature")
ok(ct["min"] == 2700 and ct["max"] == 5500, "色温控件范围 2700~5500K")
ok(v["readable"] == {}, "灯没有传感器读数")

s = dev.build_device_view({"did": "2", "name": "温湿度计",
                           "model": "miaomiaoce.sensor_ht.t2"}, SENSOR_SPEC)
ok(s["cap"]["on"] is False and s["on_guess"] is False,
   "温湿度计确认无开关能力")
ok(set(s["readable"]) == {"temperature", "humidity", "battery_level"},
   "温度/湿度/电量三项读数齐全")
ok(s["readable"]["temperature"]["siid"] == 2
   and s["readable"]["temperature"]["piid"] == 1,
   "读数带 siid/piid，可直接进批量读计划")
ok(s["controls"] == [], "只读传感器不生成控件")

empty = dev.build_device_view({"did": "3", "name": "红外遥控器",
                               "model": "miir.remote.ir01"}, {})
ok(empty["on_guess"] is False and empty["cap"]["on"] is False
   and empty["switches"] == [], "云端返回空 spec = 确认无能力（非猜测态）")
ok(devcache.save([empty]) is True, "空 spec 视图允许落盘")

guess = dev.build_device_view({"did": "4", "name": "x",
                               "model": "x.fan"}, None)
ok(guess["on_guess"] is True and guess["cap"]["on"] is None,
   "spec 拉取失败仍是猜测态（不落盘）")

# ---------------------------------------------------------------- 读数计划
plan = live.build_read_plan({"2": s}, quick=True)
ok(plan == [], "quick 不读传感器")
plan_f = live.build_read_plan({"2": s}, quick=False)
ok((("2", 2, 1) in plan_f and ("2", 2, 2) in plan_f
    and ("2", 3, 1) in plan_f), "全量轮询含三项传感器读数")
ok(len(plan_f) == len(set(plan_f)), "读计划无重复 (did,siid,piid)")

_orig_batch = live.batch_read
live.batch_read = lambda plan: {(p[0], p[1], p[2]): 23.5 for p in plan}
try:
    got = live.read_live({"2": s}, quick=False)
finally:
    live.batch_read = _orig_batch
ok(got["2"]["temperature"] == 23.5 and got["2"]["humidity"] == 23.5,
   "读数合并进 live 状态（前端可直接显示）")

# ---------------------------------------------------------------- 缓存与 model 兜底
class FakeService:
    def miot_spec(self, key):
        return ("spec-request", key)


SPEC_MAP = {
    "yeelink.light.strip2": LIGHT_SPEC,
    "miaomiaoce.sensor_ht.t2": SENSOR_SPEC,
    "miir.remote.ir01": {},
}
calls = []


def fake_call(coro, timeout=None, what=""):
    key = coro[1]
    calls.append(key)
    if key == "x.broken.model":
        raise RuntimeError("模拟网络失败")
    return SPEC_MAP.get(key, {})


cloud.call = fake_call
S["service"] = FakeService()
dev._spec_cache.clear()
dev._spec_failed.clear()
dev._spec_disk_loaded = False

ok(dev.get_spec("yeelink.light.strip2") == LIGHT_SPEC,
   "用 model 能拉到 spec（device_list 无 type 字段）")
n = len(calls)
ok(dev.get_spec("yeelink.light.strip2") == LIGHT_SPEC and len(calls) == n,
   "第二次命中内存缓存，不打云端")
ok(dev.get_spec("miir.remote.ir01") == {},
   "云端明确无 spec 返回空 dict（区别于拉取失败）")
n = len(calls)
ok(dev.get_spec("miir.remote.ir01") == {} and len(calls) == n,
   "空 spec 也被缓存，不会反复请求")
ok(dev.get_spec("x.broken.model") is None, "拉取失败返回 None")
n = len(calls)
ok(dev.get_spec("x.broken.model") is None and len(calls) == n,
   "失败进负缓存，短时不重复打云端")

# device_views：model 兜底 + 并发补齐 + 真实视图
S["devices"] = [
    {"did": "1", "name": "灯带", "model": "yeelink.light.strip2", "isOnline": True},
    {"did": "2", "name": "温湿度计", "model": "miaomiaoce.sensor_ht.t2",
     "isOnline": True},
    {"did": "3", "name": "红外遥控器", "model": "miir.remote.ir01",
     "isOnline": True},
]
views = dev.device_views()
ok(all(not x["on_guess"] for x in views.values()),
   "device_views 全部设备脱离猜测态")
ok(any(c["key"] == "brightness" for c in views["1"]["controls"]),
   "灯带视图含亮度控件")
ok("temperature" in views["2"]["readable"], "温湿度计视图含温度读数")
ok(os.path.exists(config.SPEC_CACHE_PATH), "spec 已落盘，重启免重拉")

# 磁盘缓存重载
dev._spec_cache.clear()
dev._spec_disk_loaded = False
n = len(calls)
ok(dev.get_spec("yeelink.light.strip2") == LIGHT_SPEC and len(calls) == n,
   "重启后从磁盘缓存恢复，零云端请求")

# ---------------------------------------------------------------- 模式枚举（修复滑杆误判）
MODE_SVC = svc("air-purifier", 2, [
    prop("mode", 1, "uint8", ("read", "write"), display="Mode",
         **{"value-list": [{"value": 0, "description": "自动"},
                           {"value": 1, "description": "睡眠"},
                           {"value": 2, "description": "强力"}]}),
])
mi = dev._control_item(MODE_SVC, MODE_SVC["properties"][0])
ok(mi is not None and mi["kind"] == "enum",
   "模式(uint8 + value-list) 应判为枚举而非滑杆")
ok(mi["options"] == [{"v": 0, "t": "自动"}, {"v": 1, "t": "睡眠"}, {"v": 2, "t": "强力"}],
   "模式枚举带中文名称按钮")
# 数值 + 取值范围（无命名选项）仍归滑杆，行为不变
RANGE_SVC = svc("light", 2, [
    prop("brightness", 1, "uint8", ("read", "write"), display="Brightness",
         **{"value-range": [1, 100, 1]}),
])
rb = dev._control_item(RANGE_SVC, RANGE_SVC["properties"][0])
ok(rb is not None and rb["kind"] == "range" and (rb["min"], rb["max"]) == (1, 100),
   "亮度(数值+取值范围) 仍为滑杆")

print("spec_parse_test: %d 项通过" % ok_n[0])
