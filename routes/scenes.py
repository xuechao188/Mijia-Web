"""场景接口。"""
from flask import Blueprint, jsonify, request

import logx
from services import evtlog
from services import scenes

log = logx.get("mihome.scenes.api")
bp = Blueprint("scenes", __name__)


@bp.route("/api/scenes")
def list_scenes():
    try:
        items = scenes.list_scenes()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "scenes": []}), 502
    return jsonify({"ok": True, "scenes": items})


@bp.route("/api/scenes/run", methods=["POST"])
def run_scene():
    data = request.get_json(silent=True) or {}
    sid = str(data.get("scene_id") or "")
    hid = str(data.get("home_id") or "")
    if not sid:
        return jsonify({"ok": False, "error": "缺少 scene_id"}), 400
    # home_id 缺省时从场景列表反查（CLI 只给 scene_id 也能执行）
    if not hid:
        try:
            for s in scenes.list_scenes():
                if s["scene_id"] == sid:
                    hid = s["home_id"]
                    if not data.get("owner_uid"):
                        data["owner_uid"] = s["owner_uid"]
                    break
        except Exception as e:
            log.warning("场景反查失败: %s", e)
    if not hid:
        return jsonify({"ok": False, "error": "场景不存在或缺少 home_id"}), 400
    try:
        ok = scenes.run_scene(sid, hid, data.get("owner_uid"))
    except Exception as e:
        evtlog.add("error", "场景执行失败：%s" % str(e)[:120], name=data.get("name", ""))
        return jsonify({"ok": False, "error": str(e)}), 502
    evtlog.add("scene", "执行场景：%s" % (data.get("name") or sid), name=data.get("name", ""))
    return jsonify({"ok": bool(ok)})
