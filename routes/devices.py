"""设备列表与控制接口。"""
from flask import Blueprint, jsonify, request

import logx
from services import devices as dev
from services import evtlog
from services import hints
from services import live
from services.state import S

log = logx.get("mihome.devices.api")
bp = Blueprint("devices", __name__)


def _switch_text(label):
    """开关分路的展示名。

    云端 spec 里这一路叫 "Left Switch Service"，直接拼进事件流会变成
    「开 Left Switch Service」。这里按与前端 switchLabel 同一套规则
    译成左键/中键/右键，认不出的英文一律降级成「按键」，不再原样露出。
    """
    t = str(label or "").strip().lower()
    if not t:
        return ""
    if "left" in t or "左" in t:
        return "左键"
    if "middle" in t or "center" in t or "中" in t:
        return "中键"
    if "right" in t or "右" in t:
        return "右键"
    if "toggle" in t or "切换" in t:
        return "切换"
    if "switch" in t or "按键" in t:
        return "按键"
    return str(label).strip()


@bp.route("/api/devices")
def list_devices():
    views = dev.device_views()
    return jsonify({"ok": True, "devices": list(views.values()),
                    "logged_in": bool(S["logged_in"])})


@bp.route("/api/devices/refresh", methods=["POST"])
def refresh():
    dev.refresh_devices()
    views = dev.device_views()
    return jsonify({"ok": True, "devices": list(views.values())})


@bp.route("/api/set", methods=["POST"])
def set_prop():
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")
    siid, piid = data.get("siid"), data.get("piid")
    value = data.get("value")
    if not did or siid is None or piid is None:
        return jsonify({"ok": False, "error": "参数不完整"}), 400
    try:
        live.set_prop(did, int(siid), int(piid), value)
    except Exception as e:
        hint = hints.failure_hint_for(e)
        evtlog.add("error", "控制失败：%s" % hint, did=did,
                   name=(S.get("views") or {}).get(did, {}).get("name", ""))
        return jsonify({"ok": False, "error": str(e), "hint": hint}), 502
    name = (S.get("views") or {}).get(did, {}).get("name", did)
    evtlog.add("control", "设置属性 siid=%s piid=%s = %s" % (siid, piid, value),
               did=did, name=name)
    return jsonify({"ok": True})


@bp.route("/api/switch", methods=["POST"])
def switch():
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")
    on = bool(data.get("on"))
    key = str(data.get("key") or "on")  # 多键开关指定路：on1/on2/…
    view = (S.get("views") or {}).get(did) or {}
    sws = view.get("switches") or []
    target = next((s for s in sws if s.get("key") == key), None)
    if target is None and view.get("on_siid") is not None:
        target = {"siid": view["on_siid"], "piid": view["on_piid"]}
    if target is None:
        return jsonify({"ok": False, "error": "该设备没有电源开关能力"}), 400
    try:
        live.set_prop(did, int(target["siid"]), int(target["piid"]), on)
    except Exception as e:
        hint = hints.failure_hint_for(e)
        evtlog.add("error", "开关失败：%s" % hint, did=did, name=view.get("name", ""))
        return jsonify({"ok": False, "error": str(e), "hint": hint}), 502
    label = next((s.get("label", "") for s in sws if s.get("key") == key), "")
    label = _switch_text(label)
    suffix = (" %s" % label) if (label and key != "on") else ""
    evtlog.add("control", ("开" if on else "关") + suffix,
               did=did, name=view.get("name", did))
    return jsonify({"ok": True})
