"""摄像头专项回归：spec 动作收集、参数控件暴露、取流/动作接口（含安全校验）。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="mijia-cam-")
os.environ["MIHOME_DATA_DIR"] = tmp

import app as appmod  # noqa: E402
from services import devices as devmod  # noqa: E402
from services import live as livemod  # noqa: E402
from services.state import S  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


fa = appmod.create_app()
fa.config["TESTING"] = True
c = fa.test_client()


# ---- 1. _collect_actions：把 spec 动作翻译成前端可用结构 ----
def fake_spec():
    return {
        "services": [
            {"iid": 2, "type": "urn:miot-spec-v2:service:camera-control:0000782F:chuangmi-v2:1",
             "properties": [], "actions": []},
            {"iid": 3, "type": "urn:miot-spec-v2:service:p2p-stream:00007881:chuangmi-v2:1",
             "properties": [], "actions": [
                 {"iid": 1, "type": "urn:miot-spec-v2:action:start-p2p-stream:00002839:chuangmi-v2:1"},
                 {"iid": 2, "type": "urn:miot-spec-v2:action:stop-stream:00002822:chuangmi-v2:1"}]},
            {"iid": 6, "type": "urn:miot-spec-v2:service:memory-card-management:0000784E:chuangmi-v2:1",
             "properties": [], "actions": [
                 {"iid": 1, "type": "urn:miot-spec-v2:action:format:00002831:chuangmi-v2:1"}]},
        ]
    }


acts = devmod._collect_actions(fake_spec())
ok(len(acts) == 3, "_collect_actions 收集到 3 个动作")
names = {a["name"] for a in acts}
ok(names == {"start-p2p-stream", "stop-stream", "format"}, "动作名取 URN 第 4 段标准标识符")
start = next(a for a in acts if a["name"] == "start-p2p-stream")
ok(start["siid"] == 3 and start["aiid"] == 1, "start-p2p-stream 的 siid/aiid 正确")


# ---- 2. 摄像头参数控件暴露（夜视/录像模式…）----
def cam_control_spec():
    return {
        "services": [
            {"iid": 2, "type": "urn:miot-spec-v2:service:camera-control:0000782F:chuangmi-v2:1",
             "properties": [
                 {"iid": 3, "type": "urn:miot-spec-v2:property:night-shot:00000057:chuangmi-v2:1",
                  "format": "uint8", "access": ["read", "write"],
                  "value-list": [{"value": 0, "description": "Off"},
                                 {"value": 1, "description": "On"},
                                 {"value": 2, "description": "Auto"}]},
                 {"iid": 6, "type": "urn:miot-spec-v2:property:recording-mode:0000008B:chuangmi-v2:1",
                  "format": "uint8", "access": ["read", "write"],
                  "value-list": [{"value": 1, "description": "Not Recording"},
                                 {"value": 2, "description": "All Record"},
                                 {"value": 3, "description": "Motion Record"}]},
                 {"iid": 5, "type": "urn:miot-spec-v2:property:wdr-mode:00000088:chuangmi-v2:1",
                  "format": "bool", "access": ["read", "write"]}],
             "actions": []},
        ]
    }


view = devmod.build_device_view({"did": "cam1", "name": "摄像机", "model": "chuangmi.camera.v2",
                                 "isOnline": True}, cam_control_spec())
cam_keys = {c["key"] for c in view["controls"]}
ok("night-shot" in cam_keys, "夜视 作为枚举控件暴露")
ok("recording-mode" in cam_keys, "录像模式 作为枚举控件暴露")
ok("wdr-mode" in cam_keys, "宽动态 作为布尔控件暴露")
ok(all(c["kind"] == "enum" for c in view["controls"]
       if c["key"] in ("night-shot", "recording-mode")), "枚举属性解析为 enum（非滑杆）")
# 英文枚举描述翻译成中文（spec 只给 Off/On/Auto，直接铺按钮会是英文）
night = next(c for c in view["controls"] if c["key"] == "night-shot")
ok([o["t"] for o in night["options"]] == ["关闭", "开启", "自动"], "夜视枚举值翻译为中文")
rec = next(c for c in view["controls"] if c["key"] == "recording-mode")
ok([o["t"] for o in rec["options"]] == ["不录像", "全程录像", "移动侦测录像"], "录像模式枚举值翻译为中文")
# 摄像头不应暴露电源开关（不在 TOGGLE_CATS）
ok(len(view["switches"]) == 0, "摄像头不暴露电源开关")


# ---- 3. 取流接口：设备没有 p2p-stream 动作 ----
S["views"] = {"door": {"did": "door", "name": "门铃", "actions": []}}
r = c.post("/api/camera/stream", json={"did": "door"})
d = r.get_json()
ok(d["ok"] and d["playable"] is False, "无取流动作：playable=False 且 ok=True")
ok("p2p-stream" in (d["note"] or ""), "缺少取流动作时给出明确说明")


# ---- 4. 取流接口：有动作但返回 P2P 令牌（不可播放）----
S["views"] = {"cam1": {"did": "cam1", "name": "摄像机",
                       "actions": [
                           {"siid": 3, "aiid": 1, "name": "start-p2p-stream", "svc": "p2p-stream"},
                           {"siid": 3, "aiid": 2, "name": "stop-stream", "svc": "p2p-stream"}]}}
calls = {}
def fake_action_token(did, siid, aiid, args=None):
    calls["a"] = (did, siid, aiid)
    return {"token": "abc123", "server": "p2p.mi.com"}
livemod.do_action = fake_action_token
r = c.post("/api/camera/stream", json={"did": "cam1"})
d = r.get_json()
ok(d["ok"] and d["playable"] is False, "P2P 令牌不可播放：playable=False")
ok(calls["a"] == ("cam1", 3, 1), "取流调用了正确的 start-p2p-stream (siid3,aiid1)")
ok(d["raw"] == {"token": "abc123", "server": "p2p.mi.com"}, "原始返回透传给前端")


# ---- 5. 取流接口：拿到可播放 URL ----
def fake_action_url(did, siid, aiid, args=None):
    return {"url": "https://stream.mi.com/live.m3u8"}
livemod.do_action = fake_action_url
r = c.post("/api/camera/stream", json={"did": "cam1"})
d = r.get_json()
ok(d["playable"] is True and d["url"].endswith(".m3u8"), "可播放地址：playable=True 且 url 透传")


# ---- 6. 取流接口：云端报错透传 ----
def fake_action_err(did, siid, aiid, args=None):
    raise RuntimeError("-127 client withdraw")
livemod.do_action = fake_action_err
r = c.post("/api/camera/stream", json={"did": "cam1"})
d = r.get_json()
ok(d["ok"] and d["playable"] is False and "限流" in (d["note"] or ""), "风控限流给出友好提示而非硬失败")


# ---- 7. 停止取流 ----
calls2 = {}
def fake_action_stop(did, siid, aiid, args=None):
    calls2["a"] = (did, siid, aiid)
    return {"ok": 1}
livemod.do_action = fake_action_stop
r = c.post("/api/camera/stop", json={"did": "cam1"})
d = r.get_json()
ok(d["ok"] and d["stopped"] is True, "停止取流返回成功")
ok(calls2["a"] == ("cam1", 3, 2), "停止调用了 stop-stream (siid3,aiid2)")


# ---- 8. 动作接口：安全校验 ----
# 允许的云台动作
S["views"] = {"cam1": {"did": "cam1", "name": "摄像机",
                       "actions": [
                           {"siid": 2, "aiid": 9, "name": "pan-left", "svc": "camera-control"},
                           {"siid": 3, "aiid": 1, "name": "start-p2p-stream", "svc": "p2p-stream"}]}}
def fake_action_pan(did, siid, aiid, args=None):
    return {"done": True}
livemod.do_action = fake_action_pan
r = c.post("/api/camera/action", json={"did": "cam1", "siid": 2, "aiid": 9})
d = r.get_json()
ok(d["ok"], "允许调用 spec 内的动作 (pan-left)")
# 不在 spec 内的动作被拒绝
r = c.post("/api/camera/action", json={"did": "cam1", "siid": 2, "aiid": 99})
d = r.get_json()
ok(d["ok"] is False and r.status_code == 400, "拒绝 spec 外的动作 (400)")
# 缺参数
r = c.post("/api/camera/action", json={"did": "cam1"})
d = r.get_json()
ok(r.status_code == 400, "缺少 siid/aiid 返回 400")


print("\ncamera 测试通过：%d 项" % ok_n[0])
