"""实时状态：批量读属性、写属性（开关/亮度/档位…）。

批量读：N 台设备合成 1 个云端请求（prop/get 的 params 本身就是数组）。
版本竞态：写操作递增 did 的版本号；轮询发出前拍快照，回来时比对，
期间被操作过的设备丢弃旧结果（与网络快慢无关，防"乐观更新被旧值盖回"）。
"""
import threading
import time

import logx
import services.cloud as cloud
from services.state import S

log = logx.get("mihome.live")

_ver = {}          # did -> int 版本号
_ver_lock = threading.Lock()
_batch_stat = {"devices": 0, "params": 0, "requests": 0, "ms": 0, "t": 0}


def bump_version(did):
    with _ver_lock:
        _ver[str(did)] = _ver.get(str(did), 0) + 1
        return _ver[str(did)]


def versions_snapshot():
    with _ver_lock:
        return dict(_ver)


def _stale(did, snap):
    with _ver_lock:
        return _ver.get(str(did), 0) != snap.get(str(did), 0)


def build_read_plan(views, quick=False):
    """生成 [(did, siid, piid)] 读取计划；quick 只读全部开关位（多键逐路）。"""
    plan = []
    for did, v in (views or {}).items():
        sws = v.get("switches") or []
        if not sws and v.get("on_siid") is not None:
            sws = [{"siid": v["on_siid"], "piid": v["on_piid"]}]
        for sw in sws:
            plan.append((did, sw["siid"], sw["piid"]))
        if quick:
            continue
        # 全量轮询：控件读数 + 传感器读数（温度/湿度/电量/照度…）
        extra = []
        for c in v.get("controls") or []:
            if c.get("readable"):
                extra.append((c["siid"], c["piid"]))
        for meta in (v.get("readable") or {}).values():
            if isinstance(meta, dict):
                extra.append((meta.get("siid"), meta.get("piid")))
        seen = {(p[1], p[2]) for p in plan if p[0] == did}
        for siid, piid in extra:
            if siid is None or piid is None or (siid, piid) in seen:
                continue
            seen.add((siid, piid))
            plan.append((did, siid, piid))
    return plan


def batch_read(plan):
    """一次请求读取全部 (did, siid, piid)。返回 {(did,siid,piid): value}。

    风控冷却期内直接返回空（上层沿用缓存值），避免高频轮询撞 -127。
    """
    if not plan or not S["service"] or cloud.cooling() > 0:
        return {}
    params = [{"did": d, "siid": s, "piid": p} for d, s, p in plan]
    t0 = time.time()
    out = {}
    try:
        # 按 30 条一批，防单请求过大
        for i in range(0, len(params), 30):
            chunk = params[i:i + 30]
            # miservice.miot_request 内部会自动包成 {'params': ...}，
            # 这里必须直接传数组；再包一层会回 code:-8 data type not valid。
            # 其返回值已是 result 数组，不要再取一次 ["result"]。
            resp = cloud.call(
                S["service"].miot_request("prop/get", chunk),
                what="batch_read")
            items = resp if isinstance(resp, list) else (resp or {}).get("result") or []
            for it in items:
                if it.get("code") == 0:
                    out[(str(it.get("did")), it.get("siid"), it.get("piid"))] = \
                        it.get("value")
    except Exception as e:
        log.warning("批量读失败: %s", e)
        raise
    finally:
        _batch_stat.update(devices=len({p[0] for p in plan}), params=len(plan),
                           requests=max(1, (len(params) + 29) // 30),
                           ms=int((time.time() - t0) * 1000), t=time.time())
    return out


def read_live(views, quick=False):
    """读一轮实时状态并合并成 {did: {key: value}}。丢弃期间被写过的设备。"""
    snap = versions_snapshot()
    plan = build_read_plan(views, quick=quick)
    values = batch_read(plan)
    out = {}
    for did, v in (views or {}).items():
        if _stale(did, snap):
            continue  # 这台设备刚被用户操作过，旧读数丢弃
        cur = out.setdefault(did, {})
        sws = v.get("switches") or []
        if not sws and v.get("on_siid") is not None:
            sws = [{"key": "on", "siid": v["on_siid"], "piid": v["on_piid"]}]
        for sw in sws:
            val = values.get((did, sw["siid"], sw["piid"]))
            if val is not None:
                cur[sw.get("key", "on")] = bool(val)
        if sws and "on" not in cur and "on1" in cur:
            cur["on"] = cur.get("on1")  # 兼容：卡片主状态取第一路
        if quick:
            continue
        for c in v.get("controls") or []:
            val = values.get((did, c["siid"], c["piid"]))
            if val is not None:
                cur[c["key"]] = val
        for key, meta in (v.get("readable") or {}).items():
            if not isinstance(meta, dict):
                continue
            val = values.get((did, meta.get("siid"), meta.get("piid")))
            if val is not None:
                cur[key] = val
    return out


def set_prop(did, siid, piid, value):
    """写一个属性。先递增版本号，再下发。

    真实 miservice 库 MiIOService.miot_set_props(self, did, props) 的
    props 是 (siid, piid, value) 元组列表，did 必须单独传；旧分支
    miot_request 仍用 {'did', 'siid', 'piid', 'value'} 的 dict 数组。
    """
    bump_version(did)
    if not S["service"]:
        raise RuntimeError("未登录")
    if hasattr(S["service"], "miot_set_props"):
        coro = S["service"].miot_set_props(str(did), [(siid, piid, value)])
    else:
        coro = S["service"].miot_request(
            "prop/set",
            [{"did": str(did), "siid": siid, "piid": piid, "value": value}],
        )
    return cloud.call(coro, timeout=15, what="set_prop")


def do_action(did, siid, aiid, args=None):
    bump_version(did)
    if not S["service"]:
        raise RuntimeError("未登录")
    return cloud.call(S["service"].miot_action(str(did), (siid, aiid), args),
                      timeout=15, what="action")


def batch_stats():
    return dict(_batch_stat)
