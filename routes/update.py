"""在线升级接口：关于信息 / 检测 / 应用 / 回滚 / 重启。

所有写操作都是 POST，沿用 app.py 的同源守卫与可选 Basic 认证。
重启放在响应发出之后由定时器触发，避免前端还没收到成功回执就被掐断。
"""
import os
import sys
import threading

from flask import Blueprint, jsonify

import config
import logx
from services import updater

log = logx.get("mihome.update.api")
bp = Blueprint("update", __name__)


@bp.route("/api/update/info")
def info():
    """关于弹窗的基础信息：当前版本、主页、是否已配置仓库、最近一次升级。"""
    return jsonify({
        "ok": True,
        "name": config.APP_NAME_CN,
        "version": config.VERSION,
        "homepage": updater.repo_homepage(),
        "configured": updater.configured(),
        "auto_restart": config.UPDATE_AUTO_RESTART,
        "last": updater.read_state(),
        "backups": updater.backups(),
    })


@bp.route("/api/update/check", methods=["POST"])
def check():
    return jsonify(updater.check())


@bp.route("/api/update/apply", methods=["POST"])
def apply():
    try:
        result = updater.apply()
    except updater.UpdateError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        log.exception("升级出现未预期错误")
        return jsonify({"ok": False, "error": "升级失败：%s" % e}), 500
    if result.get("ok") and result.get("auto_restart"):
        _schedule_restart()
    return jsonify(result)


@bp.route("/api/update/rollback", methods=["POST"])
def rollback():
    try:
        result = updater.rollback()
    except updater.UpdateError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if result.get("ok") and config.UPDATE_AUTO_RESTART:
        _schedule_restart()
    return jsonify(result)


@bp.route("/api/update/restart", methods=["POST"])
def restart():
    """手动重启。同样延迟触发，先让回执送达。"""
    _schedule_restart()
    return jsonify({"ok": True, "message": "服务将在 1 秒后重启"})


def _schedule_restart():
    """延迟 1 秒重启当前进程；优先重放原始启动命令，回退到 run.py。"""
    def _do():
        import time
        time.sleep(1)
        log.info("正在重启服务以加载新版本…")
        try:
            # waitress/waitress-serve 或 python run.py 启动都能重放 argv
            os.execv(sys.executable, [sys.executable] + sys.argv)
        except Exception as e:
            log.error("自动重启失败，请手动重启：%s", e)
            try:
                run_py = os.path.join(updater.APP_DIR, "run.py")
                os.execv(sys.executable, [sys.executable, run_py])
            except Exception as e2:
                log.error("回退重启也失败：%s", e2)
    threading.Thread(target=_do, name="restart", daemon=True).start()
