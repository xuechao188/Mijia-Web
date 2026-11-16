"""场景执行：列出并运行米家 App 中已创建的手动场景。

接口事实来自公开的米家云端协议（AppSceneService）：
  列表 POST /appgateway/miot/appsceneservice/AppSceneService/GetSimpleSceneList
  执行 POST /appgateway/miot/appsceneservice/AppSceneService/NewRunScene
参数结构：home_id + owner_uid + scene_id（scene_type=2 手动场景）。

这里用 miservice 的通用签名通道自己组请求，不引入 GPL 库。
仅支持"手动场景"（米家 App 里点一下就执行的那类）；自动化场景不在此列。
"""
import logx
import services.cloud as cloud
from services.state import S

log = logx.get("mihome.scenes")

_LIST_URI = "/appgateway/miot/appsceneservice/AppSceneService/GetSimpleSceneList"
_RUN_URI = "/appgateway/miot/appsceneservice/AppSceneService/NewRunScene"


def _homes_full():
    if not S["service"]:
        raise RuntimeError("未登录")
    return cloud.call(S["service"].home_list("full"), timeout=20, what="homes") or []


def _owner_uid(home_raw: dict) -> int:
    for k in ("uid", "owner", "owner_uid", "userId"):
        v = home_raw.get(k)
        if v:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    token = getattr(S.get("account"), "token", None) or {}
    for k in ("userId", "uid"):
        v = token.get(k) if isinstance(token, dict) else None
        if v:
            try:
                return int(v)
            except (TypeError, ValueError):
                pass
    return 0


def list_scenes():
    """返回 [{scene_id, name, home_id}]；接口不通时抛异常由路由层转提示。"""
    if not S["service"]:
        raise RuntimeError("未登录")
    out = []
    for h in _homes_full():
        hid = h.get("id") or h.get("home_id")
        if hid is None:
            continue
        params = {
            "app_version": 12,
            "get_type": 2,
            "home_id": str(hid),
            "owner_uid": _owner_uid(h),
        }
        try:
            resp = cloud.call(
                S["service"].miio_request(_LIST_URI, params),
                timeout=20, what="scene_list")
        except Exception as e:
            log.warning("场景列表失败 home=%s: %s", hid, e)
            continue
        items = (resp or {}).get("manual_scene_info_list") or []
        for it in items:
            sid = it.get("scene_id") or it.get("id")
            if sid is None:
                continue
            out.append({
                "scene_id": str(sid),
                "name": it.get("name") or ("场景" + str(sid)),
                "home_id": str(hid),
                "owner_uid": _owner_uid(h),
            })
    return out


def run_scene(scene_id: str, home_id: str, owner_uid: int = None):
    """执行一个手动场景。"""
    if not S["service"]:
        raise RuntimeError("未登录")
    if owner_uid is None:
        for h in _homes_full():
            if str(h.get("id") or h.get("home_id")) == str(home_id):
                owner_uid = _owner_uid(h)
                break
    params = {
        "scene_id": str(scene_id),
        "scene_type": 2,
        "phone_id": "null",
        "home_id": str(home_id),
        "owner_uid": int(owner_uid or 0),
    }
    resp = cloud.call(
        S["service"].miio_request(_RUN_URI, params),
        timeout=20, what="scene_run")
    return bool(resp)
