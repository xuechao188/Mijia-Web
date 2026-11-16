"""后端装配入口：建 Flask、注册蓝图、跑后台保活循环。

安全默认：只监听 127.0.0.1；写接口校验 Origin 同源，防 CSRF/DNS rebinding。
公网部署时由 MIHOME_HOST / MIHOME_ALLOWED_ORIGINS / MIHOME_ACCESS_* 显式放开，
三项缺一不可——详见 README「部署到虚拟主机」。
"""
import base64
import hmac
import os
import threading
import time
from urllib.parse import urlparse

from flask import Flask, jsonify, request, send_from_directory

import config
import logx
from services import cloud
from services import devices as dev
from services import evtlog
from services import live
from services import notices
from services.state import S

log = logx.get("mihome.app")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
VUE_INDEX = os.path.join(STATIC_DIR, "vue", "index.html")


def create_app() -> Flask:
    app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="/static")

    # ---- 访问密码（可选，公网部署必须开）----
    # 本机使用两项都为空，不弹登录框、不改任何现有行为。
    # 开启了就拦在所有路由之前：没有它，任何能访问端口的人都能开关设备。
    def _basic_ok() -> bool:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Basic "):
            return False
        try:
            raw = base64.b64decode(header[6:], validate=True).decode("utf-8")
            user, _, pwd = raw.partition(":")
        except Exception:
            return False
        return (hmac.compare_digest(user.encode(), config.ACCESS_USER.encode()) and
                hmac.compare_digest(pwd.encode(), config.ACCESS_PASSWORD.encode()))

    # ---- 同源守卫（写操作必须来自白名单页面）----
    # 本机恒放 127.0.0.1/localhost/[::1]；域名部署时用
    # MIHOME_ALLOWED_ORIGINS 追加自己的域名。两者都缺失（CLI / curl）放行。
    # 按主机名比对：反向代理终止 TLS 后后端看到的协议可能与浏览器不同。
    @app.before_request
    def _guard():
        if config.ACCESS_USER and config.ACCESS_PASSWORD and not _basic_ok():
            resp = jsonify({"ok": False, "error": "需要访问密码"})
            resp.status_code = 401
            resp.headers["WWW-Authenticate"] = \
                'Basic realm="Mijia-Web", charset="UTF-8"'
            return resp
        if request.method in ("POST", "PUT", "DELETE", "PATCH"):
            allowed = config.allowed_origins()
            for src in (request.headers.get("Origin") or "",
                        request.headers.get("Referer") or ""):
                if not src:
                    continue
                try:
                    src_host = (urlparse(src).hostname or "").lower()
                except ValueError:
                    src_host = ""
                if src_host not in allowed:
                    return jsonify({"ok": False, "error": "跨源请求被拒绝"}), 403
        return None

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        return resp

    from routes.auth import bp as auth_bp
    from routes.devices import bp as dev_bp
    from routes.live import bp as live_bp
    from routes.misc import bp as misc_bp
    from routes.scenes import bp as scenes_bp
    from routes.groups import bp as groups_bp
    from routes.history import bp as history_bp
    from routes.automations import bp as automations_bp
    from routes.layout import bp as layout_bp
    from routes.camera import bp as camera_bp
    from routes.notices import bp as notices_bp
    from routes.ir import bp as ir_bp
    from routes.update import bp as update_bp
    app.register_blueprint(auth_bp)
    app.register_blueprint(dev_bp)
    app.register_blueprint(live_bp)
    app.register_blueprint(misc_bp)
    app.register_blueprint(scenes_bp)
    app.register_blueprint(groups_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(automations_bp)
    app.register_blueprint(layout_bp)
    app.register_blueprint(camera_bp)
    app.register_blueprint(notices_bp)
    app.register_blueprint(ir_bp)
    app.register_blueprint(update_bp)

    @app.route("/")
    def index():
        # 新旧前端并存：MIJIA_UI=vue 时优先用构建产物；
        # 产物不存在则自动回退旧界面，避免误开环境变量导致白屏。
        if config.UI_FLAVOR == "vue" and os.path.isfile(VUE_INDEX):
            return send_from_directory(STATIC_DIR, "vue/index.html")
        return send_from_directory(STATIC_DIR, "index.html")

    @app.route("/api/ping")
    def ping():
        return jsonify({"ok": True, "version": config.VERSION,
                        "logged_in": bool(S["logged_in"])})

    if config.UI_FLAVOR == "vue" and not os.path.isfile(VUE_INDEX):
        log.warning("新版构建产物缺失，本次回退到 legacy 界面（请先在 web/ 下执行 npm run build）")
    log.info("前端版本: %s", config.UI_FLAVOR)

    return app


# ---------------------------------------------------------------- 后台循环
def _bg_loop():
    """每 20 秒一跳：定期刷新设备列表（mesh 状态保鲜）+ 未登录时静默重试恢复。"""
    ticks = 0
    while True:
        try:
            # mesh 类设备（智能通断器等）云端状态有时滞，定期主动拉列表触发刷新
            ticks += 1
            if ticks % 15 == 0 and S.get("logged_in"):
                dev.refresh_devices()
            # 未登录但本机有 token（如登录后被小米风控暂时拦截）：
            # 每 3 分钟静默重试恢复；封禁解除后自动进入登录态，
            # 前端登录页轮询到 logged_in 即自动跳主界面
            if ticks % 9 == 0 and not S.get("logged_in") \
                    and not S.get("restoring") and os.path.exists(config.TOKEN_PATH):
                threading.Thread(target=lambda: dev.restore(),
                                 name="re-restore", daemon=True).start()
            time.sleep(20)
        except Exception as e:
            log.warning("后台循环异常: %s", e)
            time.sleep(30)


def main():
    config.ensure_dirs()
    cloud.start()
    # 后台尝试恢复登录（token 存在才会有动作）
    threading.Thread(target=lambda: dev.restore(), name="restore", daemon=True).start()
    threading.Thread(target=_bg_loop, name="bg", daemon=True).start()
    # 设备通知：后台每 NOTICE_POLL_S 秒拉一轮米家消息中心，未登录时自跳过
    notices.start()
    app = create_app()
    log.info("启动 http://%s:%s", config.HOST, config.PORT)
    from waitress import serve
    serve(app, host=config.HOST, port=config.PORT, threads=8)


if __name__ == "__main__":
    main()
