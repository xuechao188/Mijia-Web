"""摄像头取流能力判定回归。

覆盖三种真实世界的结局：
  wan      —— 新 MISS/CS2 固件，PC 端有实现，可跨网络播
  lan_only —— 老 TUTK 固件，PC 端没实现，必须同局域网
  unsupported / offline —— 压根没有取流入口，或设备不在线

判定必须是「有证据才下结论」：同一个机型换网络环境，结论应当跟着变，
而不是写死一个猜测。
"""
import os
import struct
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MIHOME_DATA_DIR"] = tempfile.mkdtemp(prefix="mijia-cap-")

import app as appmod  # noqa: E402
from services import camera_cap as cap  # noqa: E402
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

P2P = [{"siid": 3, "aiid": 1, "name": "start-p2p-stream", "svc": "p2p-stream"},
       {"siid": 3, "aiid": 2, "name": "stop-stream", "svc": "p2p-stream"}]


# 探测副作用全部打桩：测试不打云端、不发 UDP
_REAL_LAN = cap._lan_reachable  # 第 9 节要拿真函数验包格式


def stub_net(pc_ip="192.168.1.198", reach=False):
    cap._local_ip_towards = lambda ip: pc_ip
    cap._lan_reachable = lambda ip, uid: reach


stub_net()


def setup(localip="192.168.31.56", online=True, actions=None, model="chuangmi.camera.v2"):
    cap.invalidate()
    stub_net()  # 回到「本机在别的网段」基线，避免上一个用例的桩串味
    S["views"] = {"cam": {"did": "cam", "name": "摄像机", "model": model,
                          "online": online, "actions": P2P if actions is None else actions}}
    S["devices"] = [{"did": "cam", "model": model, "localip": localip,
                     "p2p_id": "52K3F4LPEMZRR3LT111A", "isOnline": online}]


def fake_vendor(name):
    def _v(did):
        return {"vendor": name, "code": {"tutk": 1, "agora": 3, "cs2": 4, "mtp": 6}.get(name),
                "region": "CN", "miss": "3.1.9.0"}, None
    cap._vendor = _v


def fake_vendor_fail(did):
    return None, "云端未返回厂商信息（timeout）"


# ---- 1. 老 TUTK 固件 + 跨网段：只能局域网 ----
print("\n[1] tutk 固件 + 本机不在同网段")
setup()
fake_vendor("tutk")
r = cap.assess("cam")
ok(r["mode"] == "lan_only", "vendor=tutk 且跨网段 → lan_only")
ok(r["remote_playable"] is False, "lan_only 不可跨网络播放")
ok(r["same_lan"] is False, "同网段判定为 False")
ok("192.168.31.56" in r["advice"], "建议里给出设备所在网段")
ok("192.168.1.198" in r["advice"], "建议里给出本机出口地址")
ok(r["evidence"]["vendor"] == "tutk", "证据里留下 vendor")
ok(r["evidence"]["master_region"] == "CN", "证据里留下主服务器区域")

# ---- 2. TUTK + 同网段：可局域网直连 ----
print("\n[2] tutk 固件 + 同网段")
setup()
stub_net("192.168.31.20", True)
fake_vendor("tutk")
r = cap.assess("cam")
ok(r["mode"] == "lan", "vendor=tutk 且同网段 → lan")
ok(r["same_lan"] is True, "同网段判定为 True")
ok(r["lan_reachable"] is True, "局域网实测有回包")
ok(r["remote_playable"] is False, "同网段也不改变「不能跨网」的事实")

# ---- 3. 同网段但局域网探测无回包 ----
print("\n[3] 同网段但探测无回包")
setup()
stub_net("192.168.31.20", False)
r = cap.assess("cam")
ok(r["mode"] == "lan" and r["lan_reachable"] is False, "无回包时如实记录，不谎报可达")
ok("隔离" in r["advice"] or "局域网监控" in r["advice"], "给出可操作的排查方向")

# ---- 4. 新 CS2 固件：可跨网络 ----
print("\n[4] cs2 / mtp 固件")
setup(localip="10.0.0.8")
fake_vendor("cs2")
r = cap.assess("cam")
ok(r["mode"] == "wan", "vendor=cs2 → wan")
ok(r["remote_playable"] is True, "wan 可跨网络播放")
setup(localip="10.0.0.8")
fake_vendor("mtp")
ok(cap.assess("cam")["mode"] == "wan", "vendor=mtp → wan")

# ---- 5. agora 归入「PC 端无实现」 ----
print("\n[5] agora 固件")
setup()
fake_vendor("agora")
r = cap.assess("cam")
ok(r["mode"] == "lan_only", "vendor=agora 视作 PC 端无实现")

# ---- 6. 没有取流入口 / 设备离线 ----
print("\n[6] 没有入口 / 离线")
setup(actions=[])
fake_vendor("tutk")
r = cap.assess("cam")
ok(r["mode"] == "unsupported", "无 p2p-stream 动作 → unsupported")
ok("p2p-stream" in r["reason"], "说明缺的是哪个服务")
setup(online=False)
fake_vendor("tutk")
r = cap.assess("cam")
ok(r["mode"] == "offline", "明确离线 → offline")
ok(r["remote_playable"] is False, "离线不可播放")

# ---- 7. 拿不到厂商信息：不猜，标 unknown ----
print("\n[7] 云端没给厂商")
setup()
cap._vendor = fake_vendor_fail
r = cap.assess("cam")
ok(r["mode"] == "unknown", "没有厂商证据 → unknown（不瞎猜成可播）")
ok(r["remote_playable"] is False, "unknown 不谎报可播")
ok("timeout" in r["reason"], "把失败原因原样带出")

# ---- 8. 缓存与强制重测 ----
print("\n[8] 缓存")
setup()
fake_vendor("tutk")
first = cap.assess("cam")
ok(first.get("cached") is not True, "首次探测不打 cached 标记")
again = cap.assess("cam")
ok(again.get("cached") is True, "10 分钟内命中缓存")
cap.invalidate("cam")
third = cap.assess("cam")
ok(third.get("cached") is not True, "invalidate 后重新探测")

# ---- 9. TUTK 局域网广播包格式 ----
print("\n[9] 局域网探测包")
import socket as _s  # noqa: E402

captured = {}


class FakeSock:
    def __init__(self, *a, **k):
        pass

    def settimeout(self, t):
        pass

    def sendto(self, data, addr):
        captured["data"] = data
        captured["addr"] = addr

    def recvfrom(self, n):
        raise _s.timeout()

    def close(self):
        pass


_orig_socket = cap.socket.socket
cap.socket.socket = lambda *a, **k: FakeSock()
_REAL_LAN("192.168.31.56", "52K3F4LPEMZRR3LT111A")
cap.socket.socket = _orig_socket

pkt = captured.get("data") or b""
ok(len(pkt) == 68, "广播包 68 字节")
ok(pkt[0:3] == b"\x04\x02\x19", "magic = 04 02 19")
ok(pkt[8:11] == b"\x01\x06\x21", "指令头 = 01 06 21（stageBroadcast）")
ok(pkt[16:36] == b"52K3F4LPEMZRR3LT111A", "UID 落在偏移 16")
ok(pkt[64] == 0x01, "stage 字节为 1")
ok(struct.unpack_from("<H", pkt, 4)[0] == 52, "长度字段 = 总长-16")
ok(captured.get("addr") == ("192.168.31.56", 32761), "发往设备 32761 端口")

# ---- 10. 接口层：注定播不了就不要再去打云接口 ----
print("\n[10] /api/camera/stream 前置判定")
setup()
fake_vendor("tutk")
called = {"a": 0}
from services import live as livemod  # noqa: E402

_orig_action = livemod.do_action


def boom(*a, **k):
    called["a"] += 1
    return {"token": "x"}


livemod.do_action = boom
r = c.post("/api/camera/stream", json={"did": "cam"})
d = r.get_json()
ok(called["a"] == 0, "判定 lan_only 后不再调用云端取流动作")
ok(d["ok"] and d["playable"] is False, "返回 ok=True + playable=False")
ok(d["capability"]["mode"] == "lan_only", "把能力判定一并返回给前端")
ok("局域网" in (d["note"] or ""), "提示里讲清「需要同局域网」")


# ---- 11. 接口层：可跨网络的设备仍然真的去取流 ----
print("\n[11] wan 设备照常取流")
setup(localip="10.0.0.8")
fake_vendor("cs2")
r = c.post("/api/camera/stream", json={"did": "cam"})
d = r.get_json()
ok(called["a"] == 1, "wan 设备会真的发起取流")
ok(d["capability"]["mode"] == "wan", "返回 wan 判定")
livemod.do_action = _orig_action


# ---- 12. capability 接口 ----
print("\n[12] /api/camera/capability")
setup()
fake_vendor("tutk")
r = c.get("/api/camera/capability?did=cam")
d = r.get_json()
ok(r.status_code == 200 and d["ok"], "GET capability 返回 200")
ok(d["capability"]["mode"] == "lan_only", "接口返回判定结果")
ok("checked_at" in d["capability"], "带检测时间")
r = c.get("/api/camera/capability")
ok(r.status_code == 400, "缺 did 返回 400")
r = c.get("/api/camera/capability?did=nope")
d = r.get_json()
ok(d["ok"] and d["capability"]["mode"] == "unknown", "未知 did 返回 unknown 而不是崩")

print(f"\ncamera_cap 测试通过：{ok_n[0]} 项")
