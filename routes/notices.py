"""设备通知接口：列表 / 标记已读 / 立即检查。

数据来自 services/notices.py（后台轮询米家消息中心的未读消息），
前端只轮这个本地接口，不直接打云端。
"""
from flask import Blueprint, jsonify, request

import logx
from services import notices

log = logx.get("mihome.notice.api")
bp = Blueprint("notices", __name__)


@bp.route("/api/notices")
def list_notices():
    limit = request.args.get("limit", type=int) or 60
    return jsonify({"ok": True, **notices.snapshot(limit)})


@bp.route("/api/notices/read", methods=["POST"])
def read_notices():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids")
    if not isinstance(ids, list):
        ids = None
    left = notices.mark_read(ids)
    return jsonify({"ok": True, "unread": left, **notices.snapshot()})


@bp.route("/api/notices/refresh", methods=["POST"])
def refresh_notices():
    fresh = notices.sync()
    return jsonify({"ok": True, "new": len(fresh), **notices.snapshot()})
