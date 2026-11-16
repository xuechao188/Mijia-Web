"""卡片布局接口：尺寸覆盖 + 拖拽顺序。"""
from flask import Blueprint, jsonify, request

from services import layout as lay

bp = Blueprint("layout", __name__)


@bp.route("/api/layout", methods=["GET"])
def get_layout():
    return jsonify({"ok": True, **lay.load()})


@bp.route("/api/layout/size", methods=["POST"])
def set_size():
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "").strip()
    size = data.get("size")
    if not did or size not in ("sm", "md", "lg"):
        return jsonify({"ok": False, "error": "参数无效"}), 400
    try:
        result = lay.set_size(did, size)
    except ValueError:
        return jsonify({"ok": False, "error": "尺寸无效"}), 400
    return jsonify({"ok": True, **result})


@bp.route("/api/layout/order", methods=["POST"])
def set_order():
    data = request.get_json(silent=True) or {}
    order = data.get("order")
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        return jsonify({"ok": False, "error": "参数无效"}), 400
    result = lay.set_order(order)
    return jsonify({"ok": True, **result})
