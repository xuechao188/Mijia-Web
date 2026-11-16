"""自动化（智能场景）HTTP 接口。

只读：列表 / 详情 / 本地 payload 预览（不写云端）。
写入（全部必须显式带 confirm=true，缺确认一律 400 且不发任何请求）：
  POST /api/automations/apply          改名与启停，只改白名单字段
  POST /api/automations/create         新建（复制现有自动化的触发与动作）
  POST /api/automations/delete         删除，必须同时提交复核过的名称

2026-11-13 已在信地做过受控写入测试：等值回写 / 改名还原 / 启停还原 /
「新建 → 读回 → 删除 → 读回」闭环，最终云端快照零差异。
"""
from flask import Blueprint, jsonify, request

from services import automations as auto

bp = Blueprint("automations", __name__)


@bp.route("/api/automations")
def list_automations():
    home_id = (request.args.get("home_id") or "").strip() or None
    force = request.args.get("force") in ("1", "true", "yes")
    try:
        items = auto.list_automations(force=force, home_id=home_id)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "automations": []}), 502
    return jsonify({
        "ok": True,
        "automations": [auto.public(v) for v in items],
        "homes": auto.home_names(),
        "count": len(items),
        "enabled": sum(1 for v in items if v["enable"]),
        "writable": True,           # Edit 已验证，可改名 / 启停
        "create_supported": True,   # Edit 不带 scene_id 可新建，④ 闭环验证
        "delete_supported": True,   # Delete 已验证可真删，需名称复核
    })


@bp.route("/api/automations/detail")
def detail():
    sid = (request.args.get("scene_id") or "").strip()
    if not sid:
        return jsonify({"ok": False, "error": "缺少 scene_id"}), 400
    try:
        v = auto.raw_of(sid)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    if not v:
        return jsonify({"ok": False, "error": "自动化不存在"}), 404
    return jsonify({"ok": True, "item": auto.public(v, with_raw=True)})


@bp.route("/api/automations/preview", methods=["POST"])
def preview():
    """只生成本地 payload，不发云端请求。"""
    data = request.get_json(silent=True) or {}
    sid = str(data.get("scene_id") or "")
    if not sid:
        return jsonify({"ok": False, "error": "缺少 scene_id"}), 400
    style = data.get("style") or auto.EDIT_STYLE
    try:
        p = auto.build_edit_payload(sid, data.get("patch") or {}, style)
        if not p["changes"] and data.get("require_change"):
            return jsonify({"ok": False, "error": "与云端内容一致，没有需要写入的改动"}), 400
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "preview": auto.public_preview(p), "sent": False})


@bp.route("/api/automations/apply", methods=["POST"])
def apply():
    """真实写入云端。必须显式确认，且只接受白名单字段。"""
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return jsonify({"ok": False, "error": "缺少显式确认（confirm=true），未发送任何写请求"}), 400
    sid = str(data.get("scene_id") or "")
    if not sid:
        return jsonify({"ok": False, "error": "缺少 scene_id"}), 400
    patch = data.get("patch")
    if not isinstance(patch, dict):
        return jsonify({"ok": False, "error": "patch 必须是对象"}), 400
    if not patch:
        return jsonify({
            "ok": False,
            "error": "没有任何改动（patch 为空），没有需要写入的内容",
        }), 400
    try:
        r = auto.apply_edit(sid, patch, auto.EDIT_STYLE)
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e), "sent": False}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e), "sent": False}), 502
    return jsonify({"ok": True, "sent": True, **r})


def _write_error(e):
    """校验类错误 400，云端/网络类错误 502，绝不把失败伪装成成功。"""
    if isinstance(e, (KeyError, ValueError)):
        return jsonify({"ok": False, "error": str(e), "sent": False}), 400
    return jsonify({"ok": False, "error": str(e), "sent": False}), 502


@bp.route("/api/automations/create/preview", methods=["POST"])
def create_preview():
    """只本地生成新建 payload，不发云端请求。"""
    data = request.get_json(silent=True) or {}
    enable = data.get("enable", False)
    if not isinstance(enable, bool):
        return jsonify({"ok": False, "error": "enable 必须是布尔值"}), 400
    try:
        p = auto.build_create_payload(
            str(data.get("template_scene_id") or ""),
            data.get("name"),
            enable,
        )
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "preview": auto.public_preview(p), "sent": False})


@bp.route("/api/automations/create", methods=["POST"])
def create():
    """真实新建。必须 confirm=true + 名称 + 模板 scene_id。"""
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return jsonify({"ok": False, "error": "缺少显式确认（confirm=true），未发送任何写请求"}), 400
    sid = str(data.get("template_scene_id") or "")
    if not sid:
        return jsonify({"ok": False, "error": "缺少模板 scene_id"}), 400
    enable = data.get("enable", False)
    if not isinstance(enable, bool):
        return jsonify({"ok": False, "error": "enable 必须是布尔值"}), 400
    try:
        r = auto.apply_create(sid, data.get("name"), enable)
    except Exception as e:
        return _write_error(e)
    return jsonify({"ok": True, "sent": True, **r})


@bp.route("/api/automations/delete/preview", methods=["POST"])
def delete_preview():
    """只本地生成删除 payload，不发云端请求。"""
    data = request.get_json(silent=True) or {}
    try:
        p = auto.build_delete_payload(str(data.get("scene_id") or ""),
                                      data.get("name"))
    except (KeyError, ValueError) as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "preview": auto.public_preview(p), "sent": False})


@bp.route("/api/automations/delete", methods=["POST"])
def delete():
    """真实删除，不可逆。必须 confirm=true + scene_id + 名称复核一致。"""
    data = request.get_json(silent=True) or {}
    if data.get("confirm") is not True:
        return jsonify({"ok": False, "error": "缺少显式确认（confirm=true），未发送任何写请求"}), 400
    sid = str(data.get("scene_id") or "")
    if not sid:
        return jsonify({"ok": False, "error": "缺少 scene_id"}), 400
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        return jsonify({"ok": False, "error": "必须提交复核名称"}), 400
    try:
        # 路由层再复核一次名称：即使写入实现被替换/打桩，也不能绕过这道守卫
        auto.build_delete_payload(sid, data["name"])
        r = auto.apply_delete(sid, data["name"])
    except Exception as e:
        return _write_error(e)
    return jsonify({"ok": True, "sent": True, **r})
