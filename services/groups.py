"""自定义分组：用户自己建的分组（跨家庭/房间），持久化到数据目录。

家庭与房间来自米家云端（devices._apply_rooms），本模块只管自定义分组。
三条原则：坏文件当空分组、结构版本不符作废、写入失败不阻塞界面。
"""
import json
import os
import threading
import uuid

import config

_lock = threading.RLock()
_VERSION = 1


def _default():
    return {"version": _VERSION, "custom": []}


def _atomic_write(path, data):
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except OSError:
        return False


def load():
    """读磁盘分组；读不到/读坏/版本对不上一律返回空分组。"""
    try:
        with open(config.GROUPS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return _default()
    if not isinstance(data, dict) or data.get("version") != _VERSION:
        return _default()
    custom = data.get("custom")
    if not isinstance(custom, list):
        return _default()
    out = []
    for g in custom:
        if not isinstance(g, dict) or not g.get("id") or not g.get("name"):
            continue
        dids = [str(x) for x in (g.get("dids") or []) if x is not None]
        out.append({"id": str(g["id"]), "name": str(g["name"]),
                    "dids": list(dict.fromkeys(dids))})
    return {"version": _VERSION, "custom": out}


def save(data):
    with _lock:
        return _atomic_write(config.GROUPS_PATH, data)


def list_groups():
    return load()["custom"]


def apply(action, payload):
    """统一写入口，返回 (ok, groups, error)。

    action: create / rename / delete / add / remove
    """
    payload = payload or {}
    with _lock:
        data = load()
        groups = data["custom"]
        act = (action or "").strip()
        name = str(payload.get("name") or "").strip()[:24]
        gid = str(payload.get("id") or "")
        did = str(payload.get("did") or "")
        g = next((x for x in groups if x["id"] == gid), None)

        if act == "create":
            if not name:
                return False, groups, "分组名不能为空"
            if any(x["name"] == name for x in groups):
                return False, groups, "同名分组已存在"
            groups.append({"id": "g_" + uuid.uuid4().hex[:10],
                           "name": name, "dids": []})
        elif act == "rename":
            if not g or not name:
                return False, groups, "分组不存在或名称为空"
            if any(x["name"] == name and x["id"] != gid for x in groups):
                return False, groups, "同名分组已存在"
            g["name"] = name
        elif act == "delete":
            if not g:
                return False, groups, "分组不存在"
            groups.remove(g)
        elif act == "add":
            if not g or not did:
                return False, groups, "参数不完整"
            if did not in g["dids"]:
                g["dids"].append(did)
        elif act == "remove":
            if not g or not did:
                return False, groups, "参数不完整"
            g["dids"] = [x for x in g["dids"] if x != did]
        else:
            return False, groups, "未知操作"

        if not save(data):
            return False, groups, "写入失败"
        return True, groups, ""
