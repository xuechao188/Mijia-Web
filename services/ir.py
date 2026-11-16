"""红外设备：识别、按键表缓存、命令表生成。

米家的「红外遥控」在账号里是**虚拟设备**（did 以 ir. 开头、model 以 miir. 开头，
parent 是带红外发射器的小爱音箱）。它有两种，控制通道完全不同：

  一、品类遥控（miir.tv / miir.stb / miir.aircondition / miir.light …）
      有 MIoT spec，但**没有 on 属性**——开关是 turn-on / turn-off 这类动作，
      音量/频道/温度/风速是 xxx-up / xxx-down 动作，模式与设定温度是
      ir-mode / ir-temperature 两个**只写属性**（云端读不回来）。
      所以按「电源位」判定它永远是 false，界面上一个控件都长不出来。
      全部走 MIoT 动作与属性。

  二、自定义遥控（miir.remote / miir.wifispeaker …）
      没有 spec，按键表存在云端：/v2/irdevice/controller/keys 列键，
      /v2/irdevice/controller/key/click 按键发码（由父设备的红外发射器发出）。

两条通道必须都接：只接一条会让将近一半的红外设备仍然点不动。

红线：这两类设备都没有「状态」可读，界面只发指令，不伪造"已开启"。空调的
ir-mode / ir-temperature 是 access:["write"]，云端不返回当前值。
"""
import json
import threading
import time

import config
import logx
import services.cloud as cloud
from services.state import S

log = logx.get("mihome.ir")

IR_DID_PREFIX = "ir."
IR_MODEL_PREFIX = "miir."

# 品类：决定命令表长什么样、卡片副标题叫什么
KIND_LABELS = {
    "ac": "空调遥控",
    "tv": "电视遥控",
    "stb": "机顶盒遥控",
    "speaker": "音箱遥控",
    "light": "灯具遥控",
    "projector": "投影遥控",
    "fan": "风扇遥控",
    "remote": "自定义遥控",
}

# 型号里出现这些片段就归到对应品类（顺序敏感：aircondition 要先于 con）
_KIND_RULES = (
    ("aircondition", "ac"), ("acpartner", "ac"), ("air-conditioner", "ac"),
    ("stb", "stb"), ("tv", "tv"), ("speaker", "speaker"),
    ("projector", "projector"), ("light", "light"), ("fan", "fan"),
)

# 动作名 → (分组, 按钮文案)。未收录的按「组=其他」兜底，不隐藏。
_ACTION_ZH = {
    "turn-on": ("电源", "开机"),
    "turn-off": ("电源", "关机"),
    "volume-up": ("音量", "音量 ＋"),
    "volume-down": ("音量", "音量 －"),
    "channel-up": ("频道", "频道 ＋"),
    "channel-down": ("频道", "频道 －"),
    "mute-on": ("静音", "静音"),
    "mute-off": ("静音", "取消静音"),
    "input-source-switch": ("输入源", "切换输入源"),
    "temperature-up": ("温度", "温度 ＋"),
    "temperature-down": ("温度", "温度 －"),
    "fan-speed-up": ("风速", "风速 ＋"),
    "fan-speed-down": ("风速", "风速 －"),
    "brightness-up": ("亮度", "亮度 ＋"),
    "brightness-down": ("亮度", "亮度 －"),
}

# 分组顺序：电源永远排第一，其余按使用频率（温度不是分组，是 ir 块上的步进）
_GROUP_ORDER = ("电源", "模式", "温度", "风速", "音量",
                "频道", "静音", "输入源", "亮度", "其他")

# 只写属性的中文：模式取值与说明（spec 的 value-list 只给英文）
_MODE_ZH = {
    "auto": "自动", "cool": "制冷", "dry": "除湿", "heat": "制热",
    "fan": "送风", "ventilate": "通风",
}

# 红外设备的共同说明：单向发码，没有回读状态
STATELESS_NOTE = ("红外是单向发码：点一下就把指令发出去，云端读不回当前状态，"
                  "所以这里不显示「已开启 / 已关闭」。")

_KEYS = {}          # did -> [{id, name}]
_KEYS_AT = {}       # did -> 缓存时刻
_disk_loaded = False
_lock = threading.RLock()
_prefetch_lock = threading.Lock()
_prefetching = False


# ---------------------------------------------------------------- 识别
def is_ir(dev) -> bool:
    """红外虚拟设备的判定。did 与 model 双条件，命中任一即算。"""
    did = str((dev or {}).get("did") or "")
    model = str((dev or {}).get("model") or "")
    return did.startswith(IR_DID_PREFIX) or model.startswith(IR_MODEL_PREFIX)


def kind_of(model) -> str:
    m = str(model or "").lower()
    for key, kind in _KIND_RULES:
        if key in m:
            return kind
    return "remote"


def label_of(model) -> str:
    return KIND_LABELS.get(kind_of(model), "红外遥控")


# ---------------------------------------------------------------- 按键表缓存
def _load_disk():
    global _disk_loaded
    with _lock:
        if _disk_loaded:
            return
        _disk_loaded = True
        try:
            with open(config.IR_KEYS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for did, item in data.items():
            if not isinstance(item, dict):
                continue
            keys = item.get("keys")
            if isinstance(keys, list):
                _KEYS[str(did)] = keys
                _KEYS_AT[str(did)] = float(item.get("t") or 0)


def _save_disk():
    """只落盘当前仍存在的红外设备，避免设备移除后缓存越滚越大。"""
    with _lock:
        data = {did: {"t": _KEYS_AT.get(did, 0), "keys": keys}
                for did, keys in _KEYS.items()}
    tmp = config.IR_KEYS_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        import os
        os.replace(tmp, config.IR_KEYS_PATH)
    except OSError:
        pass


def is_stale(did) -> bool:
    _load_disk()
    with _lock:
        if str(did) not in _KEYS_AT:
            return True
        return (time.time() - _KEYS_AT[str(did)]) > config.IR_KEYS_TTL_S


def keys(did):
    """读缓存（可能为空）。取不到不算错——自定义遥控可能真的一个键都没配。"""
    _load_disk()
    with _lock:
        return list(_KEYS.get(str(did)) or [])


def refresh(did):
    """同步拉一次云端按键表。失败沿用旧缓存，不抛给界面。"""
    did = str(did)
    if not S["service"]:
        return keys(did)
    try:
        r = cloud.call(S["service"].miio_request(
            "/v2/irdevice/controller/keys", {"did": did}),
            timeout=25, what="ir_keys")
    except Exception as e:
        log.info("拉红外按键失败 %s: %s", did, e)
        return keys(did)
    raw = (r or {}).get("keys") if isinstance(r, dict) else None
    out = []
    for k in raw or []:
        if not isinstance(k, dict) or k.get("id") is None:
            continue
        out.append({
            "id": k.get("id"),
            "name": str(k.get("display_name") or k.get("name") or "按键"),
        })
    with _lock:
        _KEYS[did] = out
        _KEYS_AT[did] = time.time()
    _save_disk()
    return out


def prefetch(dids):
    """后台补齐缺失/过期的按键表：单独一条线程串行拉，带间隔防 -127。

    单飞（prefetching 标记）——device_views() 每次刷新都会调本函数，
    不能每 3 秒起一条线程把同一批设备重拉一遍。
    """
    global _prefetching
    todo = [str(d) for d in (dids or []) if d and is_stale(d)]
    if not todo:
        return 0
    with _prefetch_lock:
        if _prefetching:
            return 0
        _prefetching = True

    def run():
        global _prefetching
        try:
            for did in todo:
                if not S["logged_in"] or cloud.cooling() > 0:
                    break
                refresh(did)
                time.sleep(config.IR_PREFETCH_GAP_S)
        finally:
            _prefetching = False

    threading.Thread(target=run, daemon=True).start()
    return len(todo)


# ---------------------------------------------------------------- 命令表
def _human(name: str) -> str:
    """没收录的动作名：把连字符换成空格，不隐藏按钮，但也不伪造译名。"""
    return str(name or "").replace("-", " ").strip()


def _temp_block(svc, prop):
    """设定温度：解析成「步进」定义，而不是十几个 °C 按钮。

    空调温度是一个连续量（16–30），铺成按钮既占版面又要横着找；
    而且遥控器上本来就是「－ 26°C ＋」。下发仍走绝对值（ir-temperature），
    ± 只在前端把本地记的值挪一格——云端读不回，相对档位会越按越乱。
    """
    vr = prop.get("value-range") or []
    if len(vr) < 2:
        return None
    lo, hi = int(round(float(vr[0]))), int(round(float(vr[1])))
    step = int(round(float(vr[2]))) if len(vr) > 2 else 1
    step = max(1, step)
    if hi < lo or (hi - lo) // step > 30:   # 量程异常时不给温度控件
        return None
    # 默认 26°C（空调最常用的设定），不在量程内就退回下限
    default = 26 if lo <= 26 <= hi and (26 - lo) % step == 0 else lo
    return {
        "siid": svc.get("iid"), "piid": prop.get("iid"),
        "min": lo, "max": hi, "step": step, "default": default,
    }


def build_temp(spec):
    """spec 里的 ir-temperature → 步进定义；没有就返回 None。"""
    if not isinstance(spec, dict):
        return None
    for svc in spec.get("services") or []:
        for prop in svc.get("properties") or []:
            if "write" not in (prop.get("access") or []):
                continue
            if _prop_name(prop) != "ir-temperature":
                continue
            blk = _temp_block(svc, prop)
            if blk:
                return blk
    return None


def temp_ok(blk, value) -> bool:
    """温度是否落在该遥控器的量程与步长上（接口层越权校验）。

    只收整数度：25.5 这种不能靠 int() 截成 25 混过去，否则实际发出去的温度
    和界面上写的会差半度。
    """
    if not isinstance(blk, dict) or isinstance(value, bool):
        return False
    try:
        f = float(value)
        v = int(f)
    except (TypeError, ValueError, OverflowError):   # 含 NaN / inf / 非数字串
        return False
    if f != v:                          # 25.5 不能截成 25 混过去
        return False
    lo, hi = int(blk.get("min")), int(blk.get("max"))
    step = max(1, int(blk.get("step") or 1))
    return lo <= v <= hi and (v - lo) % step == 0


def _mode_cmds(svc, prop):
    out = []
    for v in prop.get("value-list") or []:
        raw = str(v.get("description") or v.get("value") or "").strip()
        label = _MODE_ZH.get(raw.lower()) or raw
        if not label:
            continue
        out.append({
            "id": "p:%s:%s:%s" % (svc.get("iid"), prop.get("iid"), v.get("value")),
            "kind": "set", "group": "模式", "label": label,
            "siid": svc.get("iid"), "piid": prop.get("iid"),
            "value": v.get("value"), "prop": "ir-mode",
        })
    return out


def _replaceable(prop) -> bool:
    """只把「模式」这种有限枚举做成按钮。

    volume-increase / volume-decrease 这种名字里带 increase 的 uint8 属性是
    「步长」语义，点一下发多少完全取决于取值，做成按钮只会瞎发，跳过。
    ir-temperature 也不做按钮：它是连续量，界面上是一个「－ 26°C ＋」步进，
    单独走 build_temp / /api/ir/temp。
    """
    return _prop_name(prop) == "ir-mode"


def _prop_name(prop) -> str:
    urn = str((prop or {}).get("type") or "")
    parts = urn.split(":")
    if len(parts) >= 4 and parts[2] == "property":
        return parts[3].lower()
    return str((prop or {}).get("description") or "").strip().lower()


def _action_name(act) -> str:
    urn = str((act or {}).get("type") or "")
    parts = urn.split(":")
    if len(parts) >= 4 and parts[2] == "action":
        return parts[3].lower()
    return ""


def build_cmds(spec):
    """spec → 命令表。返回按分组顺序排好的列表；没有 spec 就是空表。

    组内顺序：电源固定「开机 → 关机」（spec 里 turn-off 的 aiid 反而更小，
    照原顺序铺会把「关机」放在最左边，很容易误点）；其余按 spec 出现顺序，
    枚举值（空调模式）因此保持 自动→制冷→除湿→制热→送风 的自然次序。
    设定温度不在命令表里，它是 ir 块上的 temp 步进。
    """
    if not isinstance(spec, dict):
        return []
    out = []
    for svc in spec.get("services") or []:
        siid = svc.get("iid")
        for prop in svc.get("properties") or []:
            if "write" not in (prop.get("access") or []):
                continue
            if not _replaceable(prop):
                continue
            name = _prop_name(prop)
            if name == "ir-mode":
                out.extend(_mode_cmds(svc, prop))
        for act in svc.get("actions") or []:
            name = _action_name(act)
            if not name or act.get("iid") is None:
                continue
            # 需要入参的动作（set-channel-number / set-channel-name）在这里
            # 没有输入框可填，调用必然失败，索性不摆按钮
            if act.get("in"):
                continue
            group, label = _ACTION_ZH.get(name, ("其他", _human(name)))
            out.append({
                "id": "a:%s:%s" % (siid, act.get("iid")),
                "kind": "action", "group": group, "label": label,
                "siid": siid, "aiid": act.get("iid"), "name": name,
            })
    order = {g: i for i, g in enumerate(_GROUP_ORDER)}
    # 有温度步进（ir-temperature 的 value-range）时就不再摆相对的「温度 ±」：
    # 界面上已经是一个「－ 26°C ＋」，再来两个相对键，用户不知道该按哪个。
    if build_temp(spec):
        out = [c for c in out if c["group"] != "温度"]
    seq = {}
    for c in out:
        g = c["group"]
        if g == "电源":
            c["seq"] = {"turn-on": 0, "turn-off": 1}.get(c.get("name") or "", 2)
        else:
            c["seq"] = seq.get(g, 0)
        seq[g] = c["seq"] + 1
    # 同组内「＋ / up / increase」排在「－ / down / decrease」前面：
    # spec 里 volume-down 的 iid 常常更小，照原样铺会把减号放左边，容易误点。
    def _up(c):
        name = str(c.get("name") or "")
        return 0 if name.endswith(("up", "increase")) else 1

    out.sort(key=lambda c: (order.get(c["group"], len(order)),
                            c["seq"] if c["group"] == "电源" else _up(c),
                            c["seq"]))
    return out


def find_cmd(did, cmd_id):
    """按 id 从该设备的命令表里取一条（接口层用它防越权）。"""
    view = (S.get("views") or {}).get(str(did)) or {}
    for c in ((view.get("ir") or {}).get("cmds") or []):
        if str(c.get("id")) == str(cmd_id):
            return c
    return None


def describe(dev, spec):
    """给前端用的 ir 块：品类、按键表、命令表、温度步进、说明。"""
    did = str((dev or {}).get("did") or "")
    model = (dev or {}).get("model") or ""
    kind = kind_of(model)
    ks = keys(did)
    cmds = build_cmds(spec)
    temp = build_temp(spec)
    note = STATELESS_NOTE if (cmds or ks or temp) else ""
    return {
        "kind": kind,
        "label": KIND_LABELS.get(kind, "红外遥控"),
        "keys": ks,
        "cmds": cmds,
        "temp": temp,
        "note": note,
    }


def press(did, key_id):
    """按一个自定义按键：云端让父设备的红外发射器发码。"""
    if not S["service"]:
        raise RuntimeError("未登录")
    return cloud.call(S["service"].miio_request(
        "/v2/irdevice/controller/key/click",
        {"did": str(did), "key_id": int(key_id)}), timeout=20, what="ir_press")


def run_cmd(did, cmd):
    """执行一条命令：动作走 miot_action，属性走 prop/set。"""
    if not S["service"]:
        raise RuntimeError("未登录")
    from services import live
    if cmd.get("kind") == "action":
        return live.do_action(did, int(cmd["siid"]), int(cmd["aiid"]), [])
    if cmd.get("kind") == "set":
        return live.set_prop(did, int(cmd["siid"]), int(cmd["piid"]), cmd.get("value"))
    raise ValueError("未知命令类型")


def temp_block(did):
    """该遥控器的温度步进定义（没有就是 None）。"""
    blk = ((S.get("views") or {}).get(str(did)) or {}).get("ir") or {}
    t = blk.get("temp")
    return t if isinstance(t, dict) else None


def set_temp(did, value):
    """下发绝对温度。云端只写不读，本函数不返回任何状态。"""
    blk = temp_block(did)
    if not blk:
        raise ValueError("该遥控器没有温度控制")
    if not temp_ok(blk, value):
        raise ValueError("温度超出该遥控器的可设范围")
    if not S["service"]:
        raise RuntimeError("未登录")
    from services import live
    return live.set_prop(did, int(blk["siid"]), int(blk["piid"]), int(value))
