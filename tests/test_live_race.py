"""实时读写回归：版本竞态防护（乐观更新不被旧值盖回）、批量计划生成、属性映射防误判。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp(prefix="mijia-live-")
os.environ["MIHOME_DATA_DIR"] = tmp

from services import live  # noqa: E402
from services.devices import map_live_key, build_device_view  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


# 版本竞态：写后旧读数被丢弃
snap = live.versions_snapshot()
v1 = snap.get("d1", 0)
live.bump_version("d1")
# 模拟：轮询发出时快照是 v1，回来时版本已 +1 → 应视为 stale
ok(live._stale("d1", snap), "写操作后旧轮询结果被识别为过期")
ok(not live._stale("d2", snap), "未操作的设备不误判")

# 批量读计划
views = {
    "a": {"on_siid": 2, "on_piid": 1,
          "controls": [{"key": "brightness", "siid": 2, "piid": 3, "readable": True}]},
    "b": {"on_siid": 2, "on_piid": 1, "controls": []},
}
plan = live.build_read_plan(views, quick=True)
ok(plan == [("a", 2, 1), ("b", 2, 1)], "quick 只读电源位")
plan_full = live.build_read_plan(views, quick=False)
ok(("a", 2, 3) in plan_full and ("a", 2, 1) in plan_full, "全量含控件读数")

# 属性映射：附属服务的 on 不映射电源位（防"指示灯误关整台设备"）
extra = {"type": "urn:miot-spec-v2:service:indicator-light:00007801:xiaomi-l1:1"}
main = {"type": "urn:miot-spec-v2:service:fan:00007808:xiaomi-fan:1"}
ok(map_live_key({}, extra, {"description": "on"}) is None,
   "指示灯 on 不映射 live.on")
ok(map_live_key({}, main, {"description": "on"}) == "on", "主控 on 映射 live.on")
ok(map_live_key({}, main, {"description": "brightness"}) == "brightness",
   "亮度正确映射")

# spec 缺失时 on_guess 标记（不落盘）
v = build_device_view({"did": "9", "name": "x", "model": "x.fan"}, None)
ok(v["on_guess"] is True and v["cap"]["on"] is None,
   "spec 缺失标记 on_guess，三态为 None")

# spec 明确无 on：确认无能力
spec_no_on = {"services": [
    {"iid": 2, "type": "urn:miot-spec-v2:service:temperature:00007803:x:1",
     "properties": [{"iid": 1, "description": "temperature",
                     "format": "float", "access": ["read"]}]}]}
v2 = build_device_view({"did": "8", "name": "y"}, spec_no_on)
ok(v2["cap"]["on"] is False and v2["on_guess"] is False,
   "spec 无 on 时确认无能力（False 三态）")

# 多键开关：两个 switch service → 逐路独立开关（防"直控只控第一路"）
spec_dual = {"services": [
    {"iid": 2, "type": "urn:miot-spec-v2:service:switch:0000780C:x:1",
     "description": "开关1",
     "properties": [{"iid": 1, "description": "on", "format": "bool",
                     "access": ["read", "write"]}]},
    {"iid": 3, "type": "urn:miot-spec-v2:service:switch:0000780C:x:1",
     "description": "开关2",
     "properties": [{"iid": 1, "description": "on", "format": "bool",
                     "access": ["read", "write"]}]},
]}
vd = build_device_view({"did": "7", "name": "双键"}, spec_dual)
ok(len(vd["switches"]) == 2, "双键开关识别出 2 路独立开关")
ok([s["key"] for s in vd["switches"]] == ["on1", "on2"], "多键开关 key 逐路命名")
ok(vd["switches"][0]["siid"] == 2 and vd["switches"][1]["siid"] == 3,
   "每路映射到各自 service 的 on")

# 读取计划：多键逐路都进 quick 计划
plan_q = live.build_read_plan({"7": vd}, quick=True)
ok(("7", 2, 1) in plan_q and ("7", 3, 1) in plan_q,
   "quick 计划含全部开关路")

# 单开关 key 仍是 on
spec_single = {"services": [
    {"iid": 2, "type": "urn:miot-spec-v2:service:fan:00007808:x:1",
     "properties": [{"iid": 1, "description": "on", "format": "bool",
                     "access": ["read", "write"]}]}]}
vs = build_device_view({"did": "6", "name": "风扇"}, spec_single)
ok(vs["switches"] == [{"key": "on", "label": "开关", "siid": 2, "piid": 1}],
   "单开关保持 key=on 兼容")

print("live_race_test: %d 项通过" % ok_n[0])
