"""摄像头「能不能在 PC 上出画面」的能力探测。

为什么要这个模块：米家摄像头横跨三代 P2P 固件（TUTK / MISS-CS2 / MTP），
PC 端只有 CS2/MTP 有可用实现 —— 官方 libmiot_camera_lite 里 TUTK 通道是被
裁掉的（实机日志原文 `Can't support TUTK vendor.`）。老 TUTK 机型（比如 2017
年的 chuangmi.camera.v2）只在米家 App 的 RN 扩展里能取流，PC 客户端无论怎么
写都拿不到画面。所以界面必须先讲清「这台能不能播、不能播要满足什么条件」，
而不是让用户反复点「尝试获取画面」看一个必然失败的云错误码。

判定完全基于可复核的证据，不做猜测：
  1. spec 里有没有 p2p-stream 服务      → 没有就是「不支持取流」
  2. 设备 localip 与本机出口地址是否同网段 → 决定「同局域网」条件
  3. 向 localip 发 TUTK 局域网广播包      → 实测局域网直连是否真的通
  4. 云端 miss_get_vendor 的 vendor       → 决定 PC 端有没有实现
"""
import ipaddress
import os
import socket
import struct
import threading
import time

import logx
from services.state import S

log = logx.get("mihome.camera.cap")

# 判定缓存：did -> (结果, 过期时间)。探测要打云端 + 发 UDP，不能每次点都跑。
_TTL = 600.0
_vendor_TTL = 6 * 3600.0  # 厂商不会变，长缓存，避免反复撞风控
_cache = {}
_vendor_cache = {}
_lock = threading.Lock()

# miss_get_vendor 返回的 vendor 枚举（同 go2rtc pkg/xiaomi/getVendorName）
VENDOR_NAME = {1: "tutk", 3: "agora", 4: "cs2", 6: "mtp"}
# PC 端有可用取流实现的厂商；tutk/agora 没有
VENDOR_PC_OK = {"cs2", "mtp"}

TUTK_MAGIC = b"\x04\x02\x19"
TUTK_SDK = b"\x06\x00\x03\x03"


# ---------------------------------------------------------------- 本机网络

def _local_ip_towards(ip):
    """UDP connect 只为让内核选出口地址，不会真的发包。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, 9))
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def _same_subnet(a, b):
    """按 /24 估计是否同网段。

    严格做法要枚举每个网卡的掩码，跨平台成本高；家庭/办公网几乎都是 /24，
    并且这个判断只用来给「建议」——真正的可达性由 _lan_reachable 实测，
    所以估算误差不会把结论带偏。
    """
    try:
        na = ipaddress.ip_network(f"{a}/24", strict=False)
        return ipaddress.ip_address(b) in na
    except Exception:
        return False


def _lan_reachable(ip, uid):
    """向设备发 TUTK 局域网广播包，能回包才说明局域网真的通。

    包格式照 go2rtc pkg/tutk/ConnectByUID(stageBroadcast) 移植：
    68 字节、magic 04 02 19、cmd 01 06 21、b[64]=stage。
    """
    if not ip or not uid:
        return None
    b = bytearray(68)
    b[0:3] = TUTK_MAGIC
    b[3] = 0x02
    struct.pack_into("<H", b, 4, len(b) - 16)
    b[8:11] = b"\x01\x06\x21"
    b[16:16 + len(uid)] = uid.encode()[:20]
    b[52:56] = TUTK_SDK
    b[56:64] = os.urandom(8)
    b[64] = 0x01  # stageBroadcast
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(1.5)
    try:
        s.sendto(bytes(b), (ip, 32761))
        s.recvfrom(2048)
        return True
    except socket.timeout:
        return False
    except OSError:
        return False
    finally:
        s.close()


# ---------------------------------------------------------------- 云端证据

def _raw_device(did):
    for d in S.get("devices") or []:
        if str(d.get("did")) == str(did):
            return d
    return None


def _vendor(did):
    """云端查该设备的 P2P 厂商；失败返回 (None, 原因)。"""
    with _lock:
        hit = _vendor_cache.get(str(did))
        if hit and hit[1] > time.time():
            return hit[0], None

    import services.cloud as cloud
    svc = S.get("service")
    if not svc:
        return None, "未登录"

    data = {
        "app_pubkey": os.urandom(32).hex(),
        "did": str(did),
        "support_vendors": "TUTK_CS2_MTP",
    }
    try:
        res = cloud.call(svc.miio_request("/v2/device/miss_get_vendor", data),
                         timeout=12, what="miss_get_vendor")
    except Exception as e:
        return None, "云端未返回厂商信息（%s）" % str(e)[:60]

    if not isinstance(res, dict):
        return None, "厂商信息格式异常"
    v = (res.get("vendor") or {})
    code = v.get("vendor")
    name = VENDOR_NAME.get(code) if isinstance(code, int) else None
    region = (v.get("vendor_params") or {}).get("tutk_master_region")
    with _lock:
        _vendor_cache[str(did)] = ({"vendor": name, "code": code,
                                    "region": region, "miss": res.get("miss_version")},
                                   time.time() + _vendor_TTL)
    return {"vendor": name, "code": code, "region": region,
            "miss": res.get("miss_version")}, None


# ---------------------------------------------------------------- 判定

def _has_p2p(view):
    for a in (view or {}).get("actions") or []:
        if "p2p-stream" in (a.get("svc") or ""):
            return True
    return False


def _verdict(mode, title, reason, advice, **extra):
    out = {
        "mode": mode,
        "remote_playable": mode == "wan",
        "title": title,
        "reason": reason,
        "advice": advice,
        "checked_at": time.time(),
    }
    out.update(extra)
    return out


def assess(did, force=False):
    """返回该设备的取流能力判定（带缓存）。"""
    did = str(did)
    now = time.time()
    if not force:
        with _lock:
            hit = _cache.get(did)
            if hit and hit[1] > now:
                return dict(hit[0], cached=True)

    view = (S.get("views") or {}).get(did)
    raw = _raw_device(did)
    model = (view or {}).get("model") or (raw or {}).get("model") or ""
    # 只有明确拿到 False 才算离线：视图里没有 online 字段时不能当离线处理
    online = (view or {}).get("online")
    ev = {"model": model, "did": did}

    if not view:
        return _verdict("unknown", "未知设备", "列表里没有这台设备。",
                        "刷新设备列表后重试。", evidence=ev)

    # 1) 有没有取流入口
    if not _has_p2p(view):
        r = _verdict("unsupported", "不支持取流",
                     "该设备的 MIoT spec 里没有 p2p-stream 服务，云端不提供取流入口。",
                     "这类设备（门铃/猫眼的部分型号）只能在米家 App 里看。",
                     evidence=ev)
        _store(did, r)
        return r

    if online is False:
        r = _verdict("offline", "设备离线",
                     "云端显示该设备当前离线，任何取流方式都不会成功。",
                     "确认设备通电并已连上家里的 Wi-Fi，在米家 App 里看到在线后重试。",
                     evidence=ev)
        _store(did, r)
        return r

    # 2) 同网段 + 局域网实测
    localip = (raw or {}).get("localip") or ""
    uid = (raw or {}).get("p2p_id") or ""
    ev["localip"] = localip
    same_lan = None
    reach = None
    if localip:
        my_ip = _local_ip_towards(localip)
        ev["pc_ip"] = my_ip
        if my_ip:
            same_lan = _same_subnet(my_ip, localip)
            ev["same_lan"] = same_lan
            if same_lan:
                reach = _lan_reachable(localip, uid)
                ev["lan_reachable"] = reach

    # 3) 云端厂商
    vec, why = _vendor(did)
    vendor = (vec or {}).get("vendor")
    if vec:
        ev.update({"vendor": vendor, "vendor_code": vec.get("code"),
                   "master_region": vec.get("region"), "miss_version": vec.get("miss")})
    elif why:
        ev["vendor_error"] = why

    # 4) 结论
    if vendor in VENDOR_PC_OK:
        r = _verdict(
            "wan", "可跨网络播放",
            "该设备走 %s 固件，PC 端有对应取流实现。" % vendor.upper(),
            "直接点「获取实时画面」即可，不需要与设备在同一局域网。",
            same_lan=same_lan, lan_reachable=reach, vendor=vendor, evidence=ev,
        )
    elif vendor:
        # tutk / agora：PC 端没有可用实现
        if same_lan:
            r = _verdict(
                "lan", "需同局域网",
                "该设备是 %s 固件，PC 端没有跨网络取流实现，只能直连局域网。" % vendor.upper(),
                ("本机与设备已在同一网段（%s），点「获取实时画面」可尝试局域网直连。"
                 % localip) if reach is not False else
                ("本机与设备在同一网段，但局域网探测没有回包，请检查设备是否开启了"
                 "「局域网监控」或路由器是否隔离了无线客户端。"),
                same_lan=same_lan, lan_reachable=reach, vendor=vendor, evidence=ev,
            )
        else:
            r = _verdict(
                "lan_only", "仅支持局域网",
                ("该设备是 %s 固件（%s），PC 端没有跨网络取流实现 —— 小米官方 P2P "
                 "只开放给米家 App，PC 版原生库已裁掉该通道。"
                 % (vendor.upper(), model or "未知型号")),
                ("请把本机接到与摄像头相同的局域网再看：设备在 %s，本机出口在 %s。"
                 "或先在手机米家 App 内查看实时画面。"
                 % (localip or "未知网段", ev.get("pc_ip") or "未知")),
                same_lan=same_lan, lan_reachable=reach, vendor=vendor, evidence=ev,
            )
    else:
        # 拿不到厂商：保守按「仅局域网」处理，但如实说明证据缺失
        r = _verdict(
            "unknown", "需要先检测",
            "没能从云端拿到该设备的 P2P 厂商信息（%s），无法判断能否跨网络播放。" % (why or "未知原因"),
            "点「重新检测」再试一次；仍然失败时可先在局域网内尝试播放。",
            same_lan=same_lan, lan_reachable=reach, vendor=None, evidence=ev,
        )

    _store(did, r)
    return r


def _store(did, r):
    with _lock:
        _cache[str(did)] = (r, time.time() + _TTL)


def invalidate(did=None):
    """网络切换、设备上线状态变化后清缓存。"""
    with _lock:
        if did is None:
            _cache.clear()
        else:
            _cache.pop(str(did), None)


def summary():
    with _lock:
        return {k: v[0].get("mode") for k, v in _cache.items()}
