"""自定义分组接口（家庭/房间树由 /api/devices 的 home/room 字段构造）。"""
from flask import Blueprint, jsonify, request

from services import groups as grp

bp = Blueprint("groups", __name__)


@bp.route("/api/groups", methods=["GET", "POST"])
def groups():
    if request.method == "GET":
        return jsonify({"ok": True, "groups": grp.list_groups()})
    data = request.get_json(silent=True) or {}
    ok, result, err = grp.apply(data.get("action"), data)
    if not ok:
        return jsonify({"ok": False, "error": err, "groups": result}), 400
    return jsonify({"ok": True, "groups": result})
