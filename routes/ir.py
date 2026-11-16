"""红外遥控接口：按键表、按键发码、命令下发。

红外设备是虚拟设备，控制面有两条，缺一条就有近一半设备点不动：

  一、品类遥控（电视/机顶盒/空调/灯具）：走 MIoT 动作与只写属性。
      没有 on 属性，所以不能套 /api/switch 那套；这里按命令 id 下发，
      且**只允许本机视图清单里存在的命令**（防越权调任意 siid/aiid）。
  二、自定义遥控：走 /v2/irdevice/controller/keys 与 key/click，
      按键 id 同样要先在该设备的按键表里，未列出的 key_id 一律拒绝。

这两条都没有状态回读，接口只回「发出去了没有」，不回「现在是开还是关」。
"""
from flask import Blueprint, jsonify, request

import logx
from services import evtlog
from services import hints
from services import ir
from services.state import S

log = logx.get("mihome.ir.api")
bp = Blueprint("ir", __name__)


def _view(did):
    return (S.get("views") or {}).get(str(did))


def _ir_block(did):
    v = _view(did)
    if not v:
        return None
    blk = v.get("ir")
    if not isinstance(blk, dict):
        return None
    return blk


def _fail(e, did, what):
    hint = hints.failure_hint_for(e)
    evtlog.add("error", "红外%s失败：%s" % (what, hint), did=did,
               name=(_view(did) or {}).get("name", ""))
    return jsonify({"ok": False, "error": str(e), "hint": hint}), 502


@bp.route("/api/ir/keys")
def keys():
    """该遥控器的按键表。force=1 重新拉云端（米家侧刚加过按键时用）。"""
    did = str(request.args.get("did") or "")
    if not did:
        return jsonify({"ok": False, "error": "缺少 did"}), 400
    blk = _ir_block(did)
    if blk is None:
        return jsonify({"ok": False, "error": "该设备不是红外遥控"}), 404
    force = request.args.get("force") in ("1", "true", "yes")
    # 只有强制或缓存过期才重新拉：空结果也要缓存，否则「本来就没配按键」
    # 的遥控器（空调那类）会每开一次页面就打一次云端。
    if force or ir.is_stale(did):
        try:
            blk["keys"] = ir.refresh(did)
        except Exception as e:      # refresh 内部已兜底，这里只是最后一道
            log.warning("拉按键表失败 did=%s: %s", did, e)
    return jsonify({"ok": True, "keys": blk.get("keys") or []})


@bp.route("/api/ir/press", methods=["POST"])
def press():
    """按一个自定义按键：云端让父设备（小爱音箱）的红外发射器发码。"""
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")
    key_id = data.get("key_id")
    if not did or key_id is None:
        return jsonify({"ok": False, "error": "缺少 did / key_id"}), 400
    blk = _ir_block(did)
    if blk is None:
        return jsonify({"ok": False, "error": "该设备不是红外遥控"}), 404
    allowed = {str(k.get("id")) for k in (blk.get("keys") or [])}
    if str(key_id) not in allowed:
        return jsonify({"ok": False, "error": "该按键不在此遥控器的按键表内，已拒绝"}), 400
    try:
        ir.press(did, key_id)
    except Exception as e:
        return _fail(e, did, "发码")
    label = next((k.get("name") for k in (blk.get("keys") or [])
                  if str(k.get("id")) == str(key_id)), "按键")
    evtlog.add("control", "红外按键：%s" % label, did=did,
               name=(_view(did) or {}).get("name", ""))
    return jsonify({"ok": True})


@bp.route("/api/ir/temp", methods=["POST"])
def temp():
    """设定温度：下发绝对值（ir-temperature 属性）。

    界面上的「－ 26°C ＋」只把**本机记的最后一次发送**挪一格，这里拿到的是
    算好的绝对值。云端只写不读，所以这个接口不回「现在多少度」。
    """
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")
    value = data.get("value")
    if not did or value is None:
        return jsonify({"ok": False, "error": "缺少 did / value"}), 400
    if _ir_block(did) is None:
        return jsonify({"ok": False, "error": "该设备不是红外遥控"}), 404
    blk = ir.temp_block(did)
    if not blk:
        return jsonify({"ok": False, "error": "该遥控器没有温度控制"}), 400
    if not ir.temp_ok(blk, value):
        return jsonify({
            "ok": False,
            "error": "温度必须是 %d–%d°C 之间的整数（步长 %d）"
                     % (blk["min"], blk["max"], blk.get("step") or 1),
        }), 400
    try:
        ir.set_temp(did, value)
    except Exception as e:
        return _fail(e, did, "温度")
    label = "%d°C" % int(value)
    evtlog.add("control", "红外温度：%s" % label, did=did,
               name=(_view(did) or {}).get("name", ""))
    return jsonify({"ok": True, "value": int(value), "label": label})


@bp.route("/api/ir/cmd", methods=["POST"])
def cmd():
    """下发一条红外命令（动作或只写属性）。

    安全：cmd_id 必须出现在该设备当前的命令表里，不和前端传 siid/aiid，
    避免被改成任意设备的任意动作。
    """
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")
    cmd_id = str(data.get("cmd_id") or "")
    if not did or not cmd_id:
        return jsonify({"ok": False, "error": "缺少 did / cmd_id"}), 400
    if _ir_block(did) is None:
        return jsonify({"ok": False, "error": "该设备不是红外遥控"}), 404
    item = ir.find_cmd(did, cmd_id)
    if item is None:
        return jsonify({"ok": False, "error": "该命令不在设备清单内，已拒绝"}), 400
    try:
        ir.run_cmd(did, item)
    except Exception as e:
        return _fail(e, did, "命令")
    evtlog.add("control", "红外命令：%s" % item.get("label", ""), did=did,
               name=(_view(did) or {}).get("name", ""))
    return jsonify({"ok": True, "label": item.get("label", "")})
