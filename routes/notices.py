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


@bp.route("/api/notices/diag", methods=["POST"])
def diag_notices():
    """记录前端「测试通知」采集的浏览器诊断，便于排查系统通知为何不弹。

    只写日志、不改任何状态；诊断内容由浏览器自己上报，服务端不做信任假设，
    仅截取固定字段、限制长度后落盘。
    """
    data = request.get_json(silent=True) or {}
    def field(key, limit=300):
        return str(data.get(key, ""))[:limit]

    lines = [
        "通知诊断上报:",
        "  时间      = " + field("time", 40),
        "  浏览器    = " + field("ua", 200),
        "  页面      = " + field("origin", 200),
        "  安全上下文= " + field("secure", 20),
        "  支持API   = " + field("hasApi", 20),
        "  权限      = " + field("permission", 20),
        "  权限查询  = " + field("queryState", 20),
        "  发送结果  = " + field("testSent", 20),
        "  错误      = " + field("testError", 200),
        "  结论      = " + field("verdict", 300),
    ]
    log.info("\n".join(lines))
    return jsonify({"ok": True})
