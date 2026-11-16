"""历史读数查询：卡片批量取短窗口，抽屉按设备取长窗口。"""
from flask import Blueprint, jsonify, request

from services import history

bp = Blueprint("history", __name__)


@bp.route("/api/history")
def get_history():
    did = request.args.get("did") or None
    keys = [k for k in (request.args.get("keys") or "").split(",") if k] or None
    try:
        hours = float(request.args.get("hours") or 6)
        points = int(request.args.get("points") or 0)
    except ValueError:
        return jsonify({"ok": False, "error": "参数格式错误"}), 400
    series = history.query(did=did, hours=hours,
                           max_points=points or None, keys=keys)
    return jsonify({"ok": True, "hours": hours, "did": did or "",
                    "series": series})
