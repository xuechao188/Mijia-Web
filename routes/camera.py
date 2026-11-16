"""摄像头专项接口：实时取流（尝试）+ 动态动作（云台/取流/格式化…）。

接口事实（实机探测 chuangmi.camera.v2 / loock.cateye.v02）：
  - 小米摄像头视频走**专有 P2P 协议**，MIoT 的 start-p2p-stream 返回的是
    取流令牌/连接信息，并非浏览器可直接播放的 URL。本机若没有 ffmpeg 转码 +
    常驻中继，浏览器无法直接出画面。故 /stream 只"尽力尝试"，拿到的若不是
    可播放地址就如实返回 raw 与说明，绝不伪造播放器。
  - 摄像头的可写属性（夜视/录像模式…）走普通 /api/set，无需本模块。
  - 动作按钮全部由前端按设备 spec 动态生成，本模块只做"校验该 (siid,aiid)
    确属此设备 spec 动作"后转发，避免越权调用任意动作。
"""
from flask import Blueprint, jsonify, request

import logx
from services import camera_cap
from services import devices as dev
from services import hints
from services import live
from services.state import S

log = logx.get("mihome.camera.api")
bp = Blueprint("camera", __name__)


def _view(did):
    return (S.get("views") or {}).get(str(did))


def _p2p(did):
    """返回该设备的 p2p-stream 起停动作 (start, stop)，没有则 (None, None)。"""
    v = _view(did)
    if not v:
        return None, None
    start = stop = None
    for a in v.get("actions") or []:
        if "p2p-stream" not in (a.get("svc") or ""):
            continue
        if a.get("name") == "start-p2p-stream":
            start = a
        elif a.get("name") == "stop-stream":
            stop = a
    return start, stop


def _inspect_stream(result):
    """判断取流结果是否含浏览器可播放地址。拿不到就如实返回 raw。

    小米摄像头绝大多数情况下返回的是 P2P 令牌/连接参数（dict），没有 http/rtsp/hls
    直链，此时 playable=False，前端提示用手机米家 App 看实时画面。
    """
    url = None
    if isinstance(result, dict):
        for k in ("url", "stream_url", "play_url", "rtsp", "hls", "live_url"):
            val = result.get(k)
            if isinstance(val, str) and val.strip():
                url = val.strip()
                break
    elif isinstance(result, str) and result.strip():
        s = result.strip()
        if s.startswith("http") or "rtsp" in s or "hls" in s or s.startswith("rtmp"):
            url = s
    return bool(url), url


@bp.route("/api/camera/capability", methods=["GET"])
def capability():
    """这台设备「能不能在 PC 上出画面」——能就播，不能就讲清要满足什么条件。

    判定链见 services/camera_cap.py：spec 入口 → 同网段 → 局域网实测 → 云端厂商。
    结果按 did 缓存 10 分钟，force=1 强制重测（用户点「重新检测」时用）。
    """
    did = str(request.args.get("did") or "")
    if not did:
        return jsonify({"ok": False, "error": "缺少 did"}), 400
    force = request.args.get("force") in ("1", "true", "yes")
    if force:
        camera_cap.invalidate(did)
    try:
        cap = camera_cap.assess(did, force=force)
    except Exception as e:
        log.warning("能力探测失败 did=%s: %s", did, e)
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "capability": cap})


@bp.route("/api/camera/stream", methods=["POST"])
def stream():
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")

    # 先判定能力：注定播不了就别再打一次必然失败的云接口，直接把原因说清楚。
    try:
        cap = camera_cap.assess(did)
    except Exception as e:
        log.warning("取流前探测失败 did=%s: %s", did, e)
        cap = None
    if cap and cap.get("mode") in ("lan_only", "unsupported", "offline"):
        return jsonify({"ok": True, "playable": False, "capability": cap,
                        "note": "%s %s" % (cap.get("reason") or "", cap.get("advice") or ""),
                        "raw": None})

    start, _ = _p2p(did)
    if not start:
        return jsonify({"ok": True, "playable": False, "capability": cap,
                        "note": "该设备未暴露 MIoT 取流动作（p2p-stream），"
                                "无法从 PC 端取流。请在手机米家 App 查看实时画面。",
                        "raw": None})
    try:
        result = live.do_action(did, start["siid"], start["aiid"], [])
    except Exception as e:
        hint = hints.failure_hint_for(e)
        # -127 风控限流：明确提示稍后重试，而不是报"失败"
        if "-127" in str(e) or "client withdraw" in str(e):
            return jsonify({"ok": True, "playable": False, "capability": cap,
                            "note": "云端限流（风控退避），请 30 秒后再试。",
                            "raw": None})
        return jsonify({"ok": False, "error": str(e), "hint": hint,
                        "capability": cap, "playable": False}), 502
    playable, url = _inspect_stream(result)
    note = None
    if not playable:
        note = ("已向设备发起取流，但返回的是小米专有 P2P 连接信息，并非浏览器"
                "可直接播放的地址。PC 端出画面需要 ffmpeg 转码 + 常驻中继（当前"
                "环境不具备），请在手机米家 App 查看实时画面。")
    return jsonify({"ok": True, "playable": playable, "url": url, "capability": cap,
                    "note": note, "raw": result})


@bp.route("/api/camera/stop", methods=["POST"])
def stop():
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")
    _, stop = _p2p(did)
    if not stop:
        return jsonify({"ok": True, "stopped": False,
                        "note": "该设备没有停止取流动作。"})
    try:
        live.do_action(did, stop["siid"], stop["aiid"], [])
    except Exception as e:
        hint = hints.failure_hint_for(e)
        return jsonify({"ok": False, "error": str(e), "hint": hint}), 502
    return jsonify({"ok": True, "stopped": True})


@bp.route("/api/camera/action", methods=["POST"])
def action():
    """调用摄像头 spec 里的任意动作（云台/格式化…）。

    安全：请求的 (siid, aiid) 必须在该设备 spec 动作清单内，否则拒绝。
    """
    data = request.get_json(silent=True) or {}
    did = str(data.get("did") or "")
    siid = data.get("siid")
    aiid = data.get("aiid")
    if siid is None or aiid is None:
        return jsonify({"ok": False, "error": "缺少 siid/aiid"}), 400
    v = _view(did)
    if not v:
        return jsonify({"ok": False, "error": "设备不存在"}), 404
    allowed = {(a["siid"], a["aiid"]) for a in (v.get("actions") or [])}
    if (int(siid), int(aiid)) not in allowed:
        return jsonify({"ok": False, "error": "该动作不在设备 spec 内，已拒绝"}), 400
    try:
        result = live.do_action(did, int(siid), int(aiid), [])
    except Exception as e:
        hint = hints.failure_hint_for(e)
        return jsonify({"ok": False, "error": str(e), "hint": hint}), 502
    return jsonify({"ok": True, "result": result})
