"""实时状态接口（quick=1 只读开关，供 3 秒快轮询）。"""
from flask import Blueprint, jsonify, request

import logx
from services import devices as dev
from services import history
from services import live
from services.state import S

log = logx.get("mihome.live.api")
bp = Blueprint("live", __name__)


@bp.route("/api/live")
def get_live():
    quick = request.args.get("quick") == "1"
    # ?did= 只回读一台设备的全量读数：灯具切模式会连带改亮度/色温，
    # 前端在写成功后用它把「模式之外被改掉的值」立刻拉回来。
    one = (request.args.get("did") or "").strip()
    views = S.get("views") or {}
    if not views:
        views = dev.device_views()
    if one:
        views = {one: views[one]} if one in views else {}
    try:
        data = live.read_live(views, quick=quick)
    except Exception as e:
        log.warning("live 读取失败: %s", e)
        return jsonify({"ok": False, "error": str(e),
                        "live": S.get("live", {})}), 502
    # 合并进缓存态（quick 只覆盖开关位 on/on1/on2…，不清其他读数）
    store = S.setdefault("live", {})
    for did, cur in data.items():
        bucket = store.setdefault(did, {})
        if quick:
            for k, v in cur.items():
                if k.startswith("on"):
                    bucket[k] = v
        else:
            bucket.update(cur)
    # 全量轮询顺便采样历史读数（内部 5 分钟节流，不额外发云端请求）
    if not quick and not one:
        history.record(data)
    return jsonify({"ok": True, "quick": quick, "live": store,
                    "versions": live.versions_snapshot(),
                    "batch": live.batch_stats()})
