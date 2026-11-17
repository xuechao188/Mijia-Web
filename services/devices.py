"""设备域：登录、设备列表、spec 缓存、设备视图。

能力判定三态（防"设备开关永久消失"类 bug）：
  True   —— spec 明确有该能力
  False  —— spec 明确没有
  None   —— spec 没拉到，现在不知道（猜测仅用于界面展示，不落盘）

电源位映射防误判（防"指示灯误关整台设备"类 bug）：
  只有主控服务的 on 才映射到 live.on；
  indicator-light / additional 等附属服务的 on 一律排除。
"""
import asyncio
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from miservice import MiAccount, MiIOService

import config
import logx
import services.cloud as cloud
from services import devcache
from services import ir
from services.state import S, _LOGIN_LOCK, _OTP_CODE

log = logx.get("mihome.devices")

_spec_lock = threading.RLock()
_spec_cache = {}   # type_str/model -> spec dict；{} 表示云端明确无 spec
_spec_failed = {}  # key -> 失败时刻（短时负缓存，防每轮轮询反复打云端）
_spec_disk_loaded = False
_on_iid = {}       # did -> (siid, piid) 仅记确认过的
SPEC_FAIL_TTL = 300
SPEC_WORKERS = 5

# 主控服务判定：这些服务的 on 才是设备电源
_MAIN_SVC_HINTS = (
    "switch", "fan", "light", "air-conditioner", "outlet", "heater",
    "humidifier", "purifier", "washer", "robot", "television", "projector",
)
# 附属服务：其 on 绝不映射电源
_EXTRA_SVC_HINTS = (
    "indicator-light", "indicator", "night-light", "ambient-light",
    "backlight", "additional", "physical-controls-locked",
)

# 传感器/读数属性：MIoT 标准名 -> 前端 live 键
_SENSOR_KEYS = {
    "temperature": "temperature",
    "relative-humidity": "humidity",
    "pm2.5-density": "pm2.5-density",
    "battery-level": "battery_level",
    "filter-life-level": "filter_life",
    "water-level": "water_level",
    "illumination": "illumination",
    "co2-density": "co2",
    "tvoc-density": "tvoc",
    "motion-state": "motion",
    "contact-state": "contact",
    "power": "power",
    "voltage": "voltage",
    "electric-current": "current",
}

# 摄像头 / 安防类服务：其下"可写属性"应作为真实可控控件暴露（夜视、录像模式…），
# 即便属性名不在普通家电白名单里。门铃/猫眼的同款属性多为只读，不会变控件，
# 只会作为读数（若命中 _SENSOR_KEYS）。
_CAMERA_SVCS = ("camera-control", "video-doorbell", "motion-detection")
_CAMERA_LABELS = {
    "night-shot": ("夜视", ""),
    "recording-mode": ("录像模式", ""),
    "wdr-mode": ("宽动态", ""),
    "time-watermark": ("时间水印", ""),
    "image-rollover": ("画面翻转", "°"),
    "image-distortion-correction": ("畸变校正", ""),
    "motion-detection": ("移动侦测", ""),
    "detection-sensitivity": ("侦测灵敏度", ""),
}
# 摄像头枚举值的英文描述 → 中文（spec 的 value-list 只给英文，直接铺按钮会是 Off/On/Auto）
_CAM_OPTION_ZH = {
    "off": "关闭", "on": "开启", "auto": "自动",
    "not recording": "不录像", "all record": "全程录像",
    "motion record": "移动侦测录像",
    "low": "低", "middle": "中", "high": "高",
    "close": "关闭", "open": "开启", "manual": "手动",
}


def _opt_label(v, is_cam):
    desc = v.get("description") or str(v.get("value"))
    if is_cam:
        zh = _CAM_OPTION_ZH.get(str(desc).strip().lower())
        if zh:
            return zh
    return desc


def _urn_name(urn: str) -> str:
    """取 URN 第 4 段的 MIoT 标准标识符。

    urn:miot-spec-v2:property:color-temperature:0000000F:philips-sread9:1
                              ^^^^^^^^^^^^^^^^^^
    厂商自定义 spec（urn:yeelink-spec:property:...）同样适用。
    """
    parts = (urn or "").split(":")
    if len(parts) >= 4 and parts[2] in ("service", "property", "action", "event"):
        return parts[3].lower()
    return ""


def _prop_name(prop: dict) -> str:
    """属性标准标识符。

    真实 spec 里 description 只是英文显示名（"Switch Status" / "Brightness"），
    标识符只存在于 property URN；旧缓存与测试桩可能只有 description，故回退。
    """
    return (_urn_name(prop.get("type"))
            or (prop.get("description") or "").strip().lower())


def _atomic_write(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- 登录
async def _otp_waiter(msg: str) -> str:
    """2FA 回调：等前端提交验证码（最多 180 秒）。

    进入时置 needed=True 让前端知道要弹验证码输入框；无论提交、超时还是异常，
    都在 finally 里清掉 needed，避免状态残留让前端误判下一次登录。
    """
    _OTP_CODE["event"].clear()
    _OTP_CODE["value"] = None
    _OTP_CODE["needed"] = True
    _OTP_CODE["method"] = msg or ""
    log.info("需要二次验证: %s", msg[:120])
    try:
        if _OTP_CODE["event"].wait(180):
            return _OTP_CODE["value"] or ""
        return ""
    finally:
        _OTP_CODE["needed"] = False


def submit_otp(code: str) -> None:
    _OTP_CODE["value"] = code
    _OTP_CODE["event"].set()


async def _do_login(username, password):
    import aiohttp
    session = aiohttp.ClientSession()
    account = MiAccount(session, username, password,
                        token_store=config.TOKEN_PATH,
                        otp_callback=_otp_waiter)
    ok = await account.login("xiaomiio")
    if not ok:
        await session.close()
        return None, None, []
    service = MiIOService(account)
    # full 模式保留 isOnline / room 等字段（默认精简版会丢掉）
    devices = await service.device_list("full")
    return account, service, devices


def _harden_token_file() -> None:
    """miservice 自己写 token 时未必设权限，这里补成仅属主可读。"""
    try:
        os.chmod(config.TOKEN_PATH, 0o600)
    except OSError:
        pass


def login(username: str, password: str):
    """账号密码登录。成功返回 True。2FA 时会挂起等 submit_otp。"""
    with _LOGIN_LOCK:
        try:
            # 2FA 时 _otp_waiter 最多等 180 秒验证码，登录协程会一直挂起；
            # 超时必须大于这个窗口，否则用户还没填完验证码就被误判登录失败。
            account, service, devices = cloud.call(
                _do_login(username, password), timeout=200, what="login")
        except Exception as e:
            log.warning("登录异常: %s", e)
            return False
        if not service:
            return False
        _harden_token_file()
        S["account"], S["service"] = account, service
        S["devices"] = devices or []
        S["logged_in"] = True
        S["user"] = username
        S["last_refresh"] = time.time()
        _remember_devices(S["devices"])
        _apply_rooms()  # 登录即用云端家庭/房间层级，不必等 5 分钟后的定期刷新
        return True


def restore():
    """用本机 token 恢复登录（token 存在才尝试）。

    风控冷却期内不发起（配合调度循环的周期性重试：封禁解除后自动恢复）。
    """
    if not os.path.exists(config.TOKEN_PATH):
        return False
    _harden_token_file()   # 旧版本留下的 644 token 也顺手收紧
    if cloud.cooling() > 0:
        return False
    S["restoring"] = True
    try:
        with _LOGIN_LOCK:
            try:
                # 300s：device_list 可能被 -127 限流，递增退避重试需要时间窗；
                # restore 跑在启动后台线程，不阻塞任何请求
                account, service, devices = cloud.call(
                    _do_login_restore(), timeout=300, what="restore")
            except Exception as e:
                log.warning("恢复登录失败: %s", e)
                return False
            if not service:
                return False
            _harden_token_file()
            S["account"], S["service"] = account, service
            S["devices"] = devices or []
            S["logged_in"] = True
            S["user"] = getattr(account, "username", "") or ""
            S["last_refresh"] = time.time()
            _remember_devices(S["devices"])
            _apply_rooms()  # 恢复登录同样立即补齐家庭/房间
            return True
    finally:
        S["restoring"] = False


async def _do_login_restore():
    import aiohttp
    session = aiohttp.ClientSession()
    account = MiAccount(session, "", "",
                        token_store=config.TOKEN_PATH,
                        otp_callback=_otp_waiter)
    # 关键：MiAccount 构造后 token 恒为 None（惰性加载），
    # 必须显式从磁盘读 token，否则恢复流程永远提前退出（已修 bug）
    token = await account.token_store.load_token()
    if not token or "xiaomiio" not in token:
        await session.close()
        return None, None, []
    account.token = token
    # 备份：miservice 登录失败会删 token 文件；网络抖动不该弄丢好 token
    try:
        ok = await account.login("xiaomiio")  # 有 passToken 时静默续期
    except Exception:
        ok = False
    if not ok:
        await account.token_store.save_token(token)  # 写回备份
        await session.close()
        return None, None, []
    service = MiIOService(account)
    # 刚登录/换发 token 后拉设备列表可能被 -127 限流，递增退避重试
    devices = None
    for i in range(3):
        try:
            devices = await service.device_list("full")
            break
        except Exception as e:
            wait = cloud.rate_limit_wait(e)
            if not wait or i == 2:
                raise
            backoff = min(wait * (i + 1), 90)
            log.info("恢复登录时设备列表被限流，%d 秒后重试（第 %d/3 次）",
                     backoff, i + 1)
            await asyncio.sleep(backoff)
    return account, service, devices or []


def logout():
    S.update({"account": None, "service": None, "logged_in": False,
              "devices": [], "views": {}, "live": {}})
    try:
        if os.path.exists(config.TOKEN_PATH):
            os.remove(config.TOKEN_PATH)
    except OSError:
        pass


def _remember_devices(devices):
    """只给在线设备刷"上次在线时间"；离线设备保留旧值（这才是 last_seen 的含义）。"""
    now = time.time()
    for d in devices or []:
        if d.get("isOnline"):
            devcache.touch_seen(d.get("did"), now)


def refresh_devices():
    """刷新设备列表 + 房间映射。

    mesh 类设备（如智能通断器）的云端状态有时滞，米家 App 每次打开都会
    主动拉一次列表来触发刷新——这里对齐该行为：定期 + 手动都走本函数。
    """
    if not S["service"] or cloud.cooling() > 0:
        return S["devices"]
    try:
        devices = cloud.call(S["service"].device_list("full"), what="device_list")
        S["devices"] = devices or []
        S["last_refresh"] = time.time()
        _apply_rooms()
        _remember_devices(S["devices"])
    except Exception as e:
        if cloud.rate_limit_wait(e):
            log.info("设备列表被限流（-127），下个周期自动重试")
        else:
            log.warning("刷新设备列表失败: %s", e)
    return S["devices"]


def _rooms_from_homes(homes):
    """纯函数：home_list 结果 -> {did: (home_id, home, room_id, room)}。

    注意两点（实测）：
      - 不同家庭存在同名房间（卫生间/厨房/客厅），必须带家庭 id/name，
        不能只用房间名做扁平分组，否则会被错误合并。
      - 房间的 dids 含多键/子设备标识（1092804866.s3），需归一化到主 did；
        但 blt.3.xxx / lumi.xxx 本身就是真实 did，不能按 "." 粗暴截断。
    """
    loc = {}
    for h in homes or []:
        hid = str(h.get("id") or h.get("home_id") or "")
        hname = h.get("name") or "未命名家庭"
        for r in h.get("rooms") or []:
            info = (hid, hname, str(r.get("id") or ""), r.get("name") or "")
            for did in r.get("dids") or []:
                k = str(did)
                loc.setdefault(k, info)
                m = re.match(r"^(\d+)\.s\d+$", k)
                if m:
                    loc.setdefault(m.group(1), info)
    return loc


def apply_room_loc(devices, loc):
    """纯函数：给设备补 home/room 字段，供同步与 async 两条登录路径共用。"""
    for d in devices or []:
        info = (loc or {}).get(str(d.get("did")))
        if info:
            d["home_id"], d["home"], d["room_id"], d["room"] = info
        else:
            d["home_id"] = d["home"] = d["room_id"] = d["room"] = ""
    return devices


def _apply_rooms():
    """同步路径（登录/恢复/定期刷新）：拉云端家庭列表后应用映射。"""
    if not S["service"]:
        return
    try:
        homes = cloud.call(S["service"].home_list(), timeout=20, what="home_list")
    except Exception as e:
        log.warning("拉房间列表失败: %s", e)
        return
    apply_room_loc(S["devices"], _rooms_from_homes(homes))


# ---------------------------------------------------------------- spec
def _load_spec_disk():
    try:
        with open(config.SPEC_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: v for k, v in data.items() if isinstance(v, dict)} \
            if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _ensure_disk_cache():
    """磁盘缓存一次性灌进内存；后续命中都是纯内存查找。"""
    global _spec_disk_loaded
    with _spec_lock:
        if not _spec_disk_loaded:
            _spec_cache.update(_load_spec_disk())
            _spec_disk_loaded = True


def get_spec(type_str: str):
    """拉取并缓存 MIoT spec。

    type_str 可以是 spec type URN，也可以是设备 model —— device_list("full")
    实测只有 model（27 个字段里没有 type），旧代码只用 type 导致 96 台设备
    全部拿不到 spec、退化成 on_guess 猜测态。

    返回三态：dict 有 spec / {} 云端明确无 spec / None 拉取失败（短时负缓存）。
    """
    if not type_str or not S["service"]:
        return None
    key = str(type_str)
    _ensure_disk_cache()
    with _spec_lock:
        if key in _spec_cache:
            return _spec_cache[key]
        if time.time() - _spec_failed.get(key, 0) < SPEC_FAIL_TTL:
            return None
    try:
        spec = cloud.call(S["service"].miot_spec(type_str),
                          timeout=25, what="miot_spec")
    except Exception as e:
        log.warning("拉 spec 失败 %s: %s", type_str, e)
        with _spec_lock:
            _spec_failed[key] = time.time()
        return None
    if spec is None:
        with _spec_lock:
            _spec_failed[key] = time.time()
        return None
    spec = spec if isinstance(spec, dict) else {}
    with _spec_lock:
        _spec_cache[key] = spec
        _atomic_write(config.SPEC_CACHE_PATH, _spec_cache)
        _spec_failed.pop(key, None)
    return spec


def prefetch_specs(models, limit=None):
    """并发补齐缺失的 spec。缓存命中后只是内存扫描（微秒级）。

    实测 80 个型号、5 并发约 4 秒；只在首次启动或新增设备时真正打云端。
    失败的型号进负缓存，不会因 3 秒轮询被反复重试。
    """
    _ensure_disk_cache()
    with _spec_lock:
        todo = [str(m) for m in models
                if m and str(m) not in _spec_cache
                and time.time() - _spec_failed.get(str(m), 0) >= SPEC_FAIL_TTL]
    todo = list(dict.fromkeys(todo))
    if limit:
        todo = todo[:limit]
    if not todo or not S["service"]:
        return 0
    with ThreadPoolExecutor(max_workers=SPEC_WORKERS) as pool:
        list(pool.map(_safe_get_spec, todo))
    return len(todo)


def _safe_get_spec(key):
    try:
        return get_spec(key)
    except Exception as e:
        log.warning("拉 spec 异常 %s: %s", key, e)
        return None


# ---------------------------------------------------------------- 设备视图
def _svc_type(svc: dict) -> str:
    t = svc.get("type") or ""
    name = _urn_name(t)
    if name:
        return name
    parts = t.split(":")
    return parts[-2] if len(parts) >= 2 else t


def _is_extra_svc(svc: dict) -> bool:
    st = _svc_type(svc)
    return any(h in st for h in _EXTRA_SVC_HINTS)


def _is_main_svc(svc: dict) -> bool:
    st = _svc_type(svc)
    return any(h in st for h in _MAIN_SVC_HINTS)


def map_live_key(dev: dict, svc: dict, prop: dict):
    """属性 → 实时视图键。附属服务的 on 绝不映射为电源位。"""
    name = _prop_name(prop)
    if name == "on":
        if _is_extra_svc(svc):
            return None
        return "on"
    if name == "brightness":
        return "brightness"
    if name == "color-temperature":
        return "color_temp"
    if name in ("target-temperature",):
        return "target_temp"
    if name == "temperature":
        return "temperature"
    if name == "relative-humidity":
        return "humidity"
    if name == "mode":
        return "mode"
    if name == "fan-level":
        return "fan_level"
    if name in ("horizontal-swing", "vertical-swing"):
        return "swing"
    return _SENSOR_KEYS.get(name)


def _find_on_iid(svc: dict):
    for p in svc.get("properties") or []:
        if _prop_name(p) == "on":
            return p.get("iid")
    return None


def _collect_switches(spec):
    """收集全部独立开关位（多键开关逐路映射，防"直控只控第一路"类问题）。

    规则：
      - 附属服务（指示灯等）的 on 永远排除
      - switch 类服务每个算一路（墙壁双键/三键的 channel_1/2/3）
      - 其它主控服务（fan/light/air-conditioner…）的 on 算整机开关
    返回 (switches, on_guess_needed)：
      switches = [{key,label,siid,piid}, ...]；单开关 key="on"，多开关 key="on1"/"on2"…
    """
    chans, mains = [], []
    for svc in spec.get("services") or []:
        if _is_extra_svc(svc):
            continue
        piid = _find_on_iid(svc)
        if piid is None:
            continue
        st = _svc_type(svc)
        entry = {"siid": svc.get("iid"), "piid": piid,
                 "desc": svc.get("description") or ""}
        if "switch" in st:
            chans.append(entry)
        elif _is_main_svc(svc):
            mains.append(entry)
        else:
            mains.append(entry)  # 认不出类型时按整机开关兜底
    picked = chans if len(chans) >= 2 else (chans + mains)[:1] or mains[:1]
    if len(picked) >= 2:
        switches = []
        for i, e in enumerate(picked, 1):
            label = e["desc"] or ("第%d路" % i)
            switches.append({"key": "on%d" % i, "label": label,
                             "siid": e["siid"], "piid": e["piid"]})
    elif picked:
        switches = [{"key": "on", "label": "开关",
                     "siid": picked[0]["siid"], "piid": picked[0]["piid"]}]
    else:
        switches = []
    return switches


def _collect_actions(spec):
    """收集 spec 里的全部动作（云台/取流/格式化…），供前端动态生成按钮。

    返回 [{siid, aiid, name, svc}]；name 取动作 URN 第 4 段标准标识符
    （如 start-p2p-stream / stop-stream / pan-left …）。
    """
    acts = []
    for svc in spec.get("services") or []:
        st = _svc_type(svc)
        for a in svc.get("actions") or []:
            name = _urn_name(a.get("type"))
            if not name:
                continue
            acts.append({"siid": svc.get("iid"), "aiid": a.get("iid"),
                         "name": name, "svc": st})
    return acts


def build_device_view(dev: dict, spec):
    """把设备 + spec 翻译成前端直接可用的视图。spec 缺失时按类型猜（不落盘）。"""
    did = str(dev.get("did"))
    name = dev.get("name") or did
    model = dev.get("model") or ""
    room = dev.get("room") or ""
    online = bool(dev.get("isOnline"))
    view = {
        "did": did, "name": name, "model": model, "room": room,
        "home": dev.get("home") or "", "home_id": dev.get("home_id") or "",
        "room_id": dev.get("room_id") or "",
        "online": online, "on": None, "on_siid": None, "on_piid": None,
        "on_guess": False, "cap": {}, "controls": [], "readable": {},
        "switches": [], "product": "", "actions": [], "ir": None,
    }
    # 红外遥控（虚拟设备，did=ir.*）：没有 on 属性，控制面在动作与按键表上。
    # 这条分支必须早于开关判定——否则它会被判成"没有电源能力"，界面上
    # 一个可点的东西都不长（正是以前的症状）。
    if ir.is_ir(dev):
        view["cap"]["on"] = False          # 无线开关可言，绝不伪造
        view["ir"] = ir.describe(dev, spec)
        view["product"] = ir.label_of(model)
        if spec:
            view["actions"] = _collect_actions(spec)
        return view
    # 产品名兜底（用户反馈：副标题别露英文型号）：spec 描述 > 型号
    view["product"] = (spec.get("description") or model) if spec else model

    if spec is None:
        # spec 没拉到（网络/风控）：按型号猜一个开关位，仅供界面展示
        # （on_guess=True 不落盘，避免半成品覆盖好快照）
        view["cap"]["on"] = None
        view["on_guess"] = True
        view["on_siid"], view["on_piid"] = 2, 1  # 经验值，仅展示
        view["switches"] = [{"key": "on", "label": "开关", "siid": 2, "piid": 1}]
        return view

    # spec == {}：云端明确没有 MIoT spec（个别老设备）。
    # 这是「确认无能力」而非「不知道」，不标 on_guess，允许落盘。
    # 红外遥控同样没有 spec，但它在那条分支里已经提前返回了。
    switches = _collect_switches(spec)
    if switches:
        view["cap"]["on"] = True
        view["switches"] = switches
        # 兼容字段：指向第一路（单开关即整机开关）
        view["on_siid"], view["on_piid"] = switches[0]["siid"], switches[0]["piid"]
        _on_iid[did] = (switches[0]["siid"], switches[0]["piid"])
    else:
        view["cap"]["on"] = False

    # 控件与读数：能力判定只认 URN 里的标准标识符
    for svc in spec.get("services") or []:
        for p in svc.get("properties") or []:
            pname = _prop_name(p)
            key = map_live_key(dev, svc, p)
            if (key and pname in _SENSOR_KEYS
                    and "read" in (p.get("access") or [])):
                view["readable"][key] = {
                    "siid": svc.get("iid"), "piid": p.get("iid"),
                    "unit": p.get("unit") or "",
                }
            if _is_extra_svc(svc) and pname == "on":
                continue
            item = _control_item(svc, p)
            if item:
                view["controls"].append(item)
    # 动作（云台/取流/存储卡…）：前端按 spec 动态生成按钮
    view["actions"] = _collect_actions(spec)
    return view


def _control_item(svc: dict, p: dict):
    desc = _prop_name(p)
    st = _svc_type(svc)
    is_cam = any(c in st for c in _CAMERA_SVCS)
    fmt = p.get("format") or ""
    access = p.get("access") or []
    writable = "write" in access
    readable = "read" in access
    if desc in ("on",) and _is_extra_svc(svc):
        return None
    labels = {
        "brightness": ("亮度", "%"), "color-temperature": ("色温", "K"),
        "target-temperature": ("目标温度", "°C"), "mode": ("模式", ""),
        "fan-level": ("风速档位", ""), "speed-level": ("风速", "%"),
        "horizontal-swing": ("左右摆风", ""), "vertical-swing": ("上下摆风", ""),
        "target-humidity": ("目标湿度", "%"), "volume": ("音量", "%"),
        "off-delay-time": ("延时关机", "分钟"),
    }
    # 合并摄像头/安防标签：仅当属性所在服务确属摄像/安防类时才算控件，
    # 避免其它设备误暴露 night-shot 之类同名属性。
    if desc not in labels and not (is_cam and desc in _CAMERA_LABELS):
        return None
    if desc == "on":
        return None  # 电源位由卡片快捷开关处理；摄像头不在 TOGGLE_CATS，不显示电源
    label, unit = labels.get(desc) or _CAMERA_LABELS.get(desc, (desc, ""))
    item = {
        "key": desc, "label": label, "unit": unit,
        "siid": svc.get("iid"), "piid": p.get("iid"),
        "writable": writable, "readable": readable,
        "svc": st,
    }
    # 有命名选项（value-list）的属性一律按枚举处理——即便格式是 uint8 之类
    # 的数值类型（米家「模式/档位」常用 uint8 + value-list，之前被误判成滑杆）。
    vl = p.get("value-list")
    if fmt == "bool":
        item["kind"] = "bool"
    elif vl:
        item["kind"] = "enum"
        item["options"] = [{"v": v.get("value"), "t": _opt_label(v, is_cam)} for v in vl]
    elif fmt in ("uint8", "uint16", "uint32", "int32", "float") or fmt.startswith("uint") or fmt.startswith("int"):
        vr = p.get("value-range")
        if vr and len(vr) >= 2:
            item["kind"] = "range"
            item["min"], item["max"], item["step"] = vr[0], vr[1], (vr[2] if len(vr) > 2 else 1)
        else:
            item["kind"] = "range"
            item["min"], item["max"], item["step"] = 0, 100, 1
    else:
        # 既非布尔、又无命名选项、也非数值范围：没有可用的离散/连续取值，丢弃
        return None
    return item


def device_views():
    """全部设备视图（优先缓存秒开；首次并发补齐 spec 后全量命中内存）。"""
    devices = S["devices"] or []
    if devices and S["service"]:
        # device_list 只给 model，没有 type；用 model 兜底拉 spec
        prefetch_specs([d.get("type") or d.get("model") for d in devices])
        # 红外遥控的按键表也在云端，后台串行补齐（不阻塞本次渲染）
        ir.prefetch([d.get("did") for d in devices if ir.is_ir(d)])
    views = {}
    cache = devcache.load()
    cache_map = {}
    if cache:
        devcache.merge_seen_from_cache(cache)
        cache_map = {str(d["did"]): d for d in cache["devices"]}
    for d in devices:
        did = str(d.get("did"))
        spec = get_spec(d.get("type") or d.get("model"))
        # 红外设备不进缓存短路：它的按键表是异步补齐的，缓存里那份可能是旧的，
        # 而重建它只花一次内存查表（spec 早已在磁盘缓存里）。
        if spec is None and did in cache_map and not ir.is_ir(d):
            v = cache_map[did]
            v["online"] = bool(d.get("isOnline"))
            # 家庭/房间以当前云端为准，旧缓存里的过期分组不能覆盖
            for k in ("home", "home_id", "room", "room_id"):
                v[k] = d.get(k) or ""
            v["last_seen"] = devcache.seen_map().get(did)
            views[did] = v
            continue
        v = build_device_view(d, spec)
        v["last_seen"] = devcache.seen_map().get(did)
        views[did] = v
    S["views"] = views
    # 只有全部确认能力后才落盘（on_guess 任一存在则 save 自动拒绝）
    devcache.save(list(views.values()), devcache.seen_map())
    return views
