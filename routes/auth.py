"""登录相关接口（账号密码 + 扫码登录）。"""
from flask import Blueprint, Response, jsonify, request

import logx
from services import devices as dev
from services import qrauth
from services.state import S

log = logx.get("mihome.auth")
bp = Blueprint("auth", __name__)


@bp.route("/api/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    if not username or not password:
        return jsonify({"ok": False, "error": "请填写账号和密码"}), 400
    ok = dev.login(username, password)
    if ok:
        return jsonify({"ok": True, "user": S["user"]})
    return jsonify({"ok": False,
                    "error": "登录失败：请检查账号密码；如需验证码请查看事件流提示后提交"}), 401


@bp.route("/api/otp", methods=["POST"])
def otp():
    data = request.get_json(silent=True) or {}
    dev.submit_otp((data.get("code") or "").strip())
    return jsonify({"ok": True})


@bp.route("/api/logout", methods=["POST"])
def logout():
    qrauth.stop()
    dev.logout()
    return jsonify({"ok": True})


@bp.route("/api/status")
def status():
    return jsonify({
        "logged_in": bool(S["logged_in"]),
        "restoring": bool(S.get("restoring")),
        "user": S.get("user", ""),
        "devices": len(S.get("devices") or []),
    })


# ---------------- 扫码登录 ----------------
@bp.route("/api/login/qr/start", methods=["POST"])
def qr_start():
    if S.get("logged_in"):
        return jsonify({"ok": False, "error": "已登录"})
    ok = qrauth.start()
    return jsonify({"ok": ok,
                    "error": qrauth.error() if not ok else "",
                    "status": qrauth.status()})


@bp.route("/api/login/qr/image")
def qr_image():
    data = qrauth.png()
    if not data:
        return jsonify({"ok": False, "error": "二维码未生成"}), 404
    return Response(data, mimetype="image/png",
                    headers={"Cache-Control": "no-store"})


@bp.route("/api/login/qr/poll")
def qr_poll():
    return jsonify({"status": qrauth.status(),
                    "error": qrauth.error(),
                    "logged_in": bool(S["logged_in"]),
                    "restoring": bool(S.get("restoring"))})
