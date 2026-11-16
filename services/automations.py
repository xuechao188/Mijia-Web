"""米家自动化（智能场景）服务：列表 / 详情 / 编辑 / 创建 / 删除。

接口事实（2026-11-13 用已登录会话实测）：
  POST /appgateway/miot/appsceneservice/AppSceneService/GetSceneList
    {"home_id": "...", "owner_uid": 1000001, "app_version": 12, "scene_type": 1}
    -> {"scene_info_list": [...19 条自动化...], "distance_ceiling": ...}
  scene_type=1 只返回自动化；get_type=1 返回手动场景（5 条）；
  get_type=2 返回全部（24 条，正好 5+19）。

  POST /appgateway/miot/appsceneservice/AppSceneService/Edit
    payload 必须是「平铺（flat）」：scene 的 33 个字段直接放顶层，
    外加 home_id / owner_uid。成功返回
      {"scene_id": "...", "activated": false, "trigger_order": 0}
    wrapped（{"scene_info": {...}}）会被服务端判为名称为空：
      code -401300002 / "scene name is nil or all spaces"
    受控写入测试（信地已停用条目）已验证：
      等值回写内容零改动、改名 + 还原、enable 切换 + 还原，均读回一致。
    另外：Create / CreateScene / Enable 等 22 个候选路由均 404。
    新建复用同一个 Edit：payload 不带 scene_id 键，且必须带有效
    scene_trigger / scene_action、temporary=false（true 会创建出任何列表
    参数都查不到的幽灵条目）。④ 受控测试已验证「创建 → 读回 → 删除 →
    读回」闭环零残留。

  POST /appgateway/miot/appsceneservice/AppSceneService/Delete
    {"scene_id": "...", "home_id": "...", "owner_uid": ...,
     "app_version": 12, "scene_type": 1} -> true（幂等，实测能真删）

  编辑只允许改 EDITABLE 白名单里的字段；删除必须复核名称，绝不触碰身份字段。

字段说明（来自真实返回）：
  scene_trigger / scene_condition / scene_action / scene_else_action
    均为 {"express": 0|1, "triggers|conditions|actions": [ {...} ]}
  单元里 name 是米家 App 显示的中文文案，extra_json / payload_json
  含 device_name / did / model，value_json 是阈值。
  enable 是启停位；type 0/1 是自动化子类型。
"""
import copy
import json
import time

import logx
import services.cloud as cloud
from services import scenes
from services.state import S

log = logx.get("mihome.automations")

_LIST_URI = "/appgateway/miot/appsceneservice/AppSceneService/GetSceneList"
_EDIT_URI = "/appgateway/miot/appsceneservice/AppSceneService/Edit"
_DELETE_URI = "/appgateway/miot/appsceneservice/AppSceneService/Delete"
_RUN_URI = "/appgateway/miot/appsceneservice/AppSceneService/RunScene"

# 新建时绝不能带的身份 / 时间字段：带 scene_id 会变成「编辑」而不是新建
_CREATE_DROP = {
    "scene_id", "scene_id_v1", "us_id", "usId", "create_time", "update_time",
    "owner_uid", "creator",
}

_TTL = 60
_CACHE = {"ts": 0.0, "items": None, "homes": None}

# 白名单：编辑时只允许改这些顶层字段，防止把 scene_id / uid 等身份字段改坏
EDITABLE = {
    "name", "enable", "enable_push", "enable_consist", "no_record_log",
    "scene_trigger", "scene_condition", "scene_action", "scene_else_action",
    "timewindow", "tags", "icon_url",
}

_BLOCK_KEY = {
    "scene_trigger": "triggers",
    "scene_condition": "conditions",
    "scene_action": "actions",
    "scene_else_action": "actions",
}


def _as_dict(v):
    if isinstance(v, dict):
        return v
    if isinstance(v, str):
        try:
            d = json.loads(v)
            return d if isinstance(d, dict) else {}
        except (ValueError, TypeError):
            return {}
    return {}


def _entries(block, field):
    """把触发/条件/动作单元解析成可读条目。"""
    b = _as_dict(block)
    out = []
    for e in b.get(_BLOCK_KEY.get(field, "actions")) or []:
        if not isinstance(e, dict):
            continue
        extra = _as_dict(e.get("extra_json"))
        payload = _as_dict(e.get("payload_json"))
        device = (extra.get("device_name") or payload.get("device_name") or "")
        name = e.get("name") or ""
        val = e.get("value_json") if "value_json" in e else (e.get("value") or "")
        out.append({
            "id": e.get("id"),
            "key": e.get("key") or "",
            "name": name,
            "device": device,
            "did": extra.get("did") or payload.get("did") or "",
            "model": extra.get("model") or payload.get("model") or "",
            "value": val,
            "text": (str(device) + " " + str(name)).strip() or (e.get("key") or "未知"),
        })
    return out


def _join(entries, sep, express=0):
    if not entries:
        return ""
    return (" 或 " if express == 1 else sep).join(x["text"] for x in entries)


def view_of(raw, home_name=""):
    """单条自动化 -> 前端视图（不含原始大对象，详情接口再单独给）。"""
    trg_block = _as_dict(raw.get("scene_trigger"))
    cond_block = _as_dict(raw.get("scene_condition"))
    trg = _entries(trg_block, "scene_trigger")
    cond = _entries(cond_block, "scene_condition")
    act = _entries(raw.get("scene_action"), "scene_action")
    els = _entries(raw.get("scene_else_action"), "scene_else_action")
    trigger_text = _join(trg, " 且 ", trg_block.get("express", 0))
    condition_text = _join(cond, " 且 ", cond_block.get("express", 0))
    action_text = _join(act, "、")
    else_text = _join(els, "、")
    summary = ("当 " + trigger_text) if trigger_text else (raw.get("name") or "自动化")
    if condition_text:
        summary += "，且 " + condition_text
    if action_text:
        summary += "，执行 " + action_text
    if else_text:
        summary += "；否则 " + else_text
    return {
        "scene_id": str(raw.get("scene_id") or ""),
        "name": raw.get("name") or ("自动化 " + str(raw.get("scene_id") or "")),
        "home_id": str(raw.get("home_id") or ""),
        "home_name": home_name,
        "uid": str(raw.get("uid") or ""),
        "enable": bool(raw.get("enable")),
        "type": raw.get("type"),
        "common_use": bool(raw.get("common_use")),
        "create_time": raw.get("create_time") or "",
        "update_time": raw.get("update_time") or "",
        "triggers": trg,
        "conditions": cond,
        "actions": act,
        "else_actions": els,
        "trigger_text": trigger_text,
        "condition_text": condition_text,
        "action_text": action_text,
        "else_text": else_text,
        "summary": summary,
        "counts": {"trigger": len(trg), "condition": len(cond),
                   "action": len(act), "else": len(els)},
        "timewindow": _as_dict(raw.get("timewindow")),
    }


def _request(params, what="automation_list"):
    if not S.get("service"):
        raise RuntimeError("未登录")
    return cloud.call(S["service"].miio_request(_LIST_URI, params),
                      timeout=20, what=what)


def _fetch():
    homes = scenes._homes_full()
    out, home_names = [], []
    for h in homes:
        hid = h.get("id") or h.get("home_id")
        if hid is None:
            continue
        hname = h.get("name") or ("家庭 " + str(hid))
        home_names.append({"id": str(hid), "name": hname})
        params = {
            "home_id": str(hid),
            "owner_uid": scenes._owner_uid(h),
            "app_version": 12,
            "scene_type": 1,
        }
        try:
            resp = _request(params)
        except Exception as e:
            log.warning("自动化列表失败 home=%s: %s", hname, e)
            continue
        for raw in (resp or {}).get("scene_info_list") or []:
            if not isinstance(raw, dict) or not raw.get("scene_id"):
                continue
            v = view_of(raw, hname)
            v["_raw"] = raw
            v["_owner_uid"] = scenes._owner_uid(h)
            out.append(v)
    return out, home_names


def list_automations(force=False, home_id=None):
    """只读列出自动化。force=True 绕过 60 秒缓存重新拉云端。"""
    now = time.time()
    cached = _CACHE["items"]
    if cached is None or force or now - _CACHE["ts"] >= _TTL:
        if cloud.cooling() > 0 and cached is not None:
            log.info("风控冷却中，自动化列表沿用缓存")
        else:
            items, homes = _fetch()
            _CACHE.update(ts=now, items=items, homes=homes)
            cached = items
    if home_id:
        return [v for v in cached if v["home_id"] == str(home_id)]
    return list(cached)


def home_names():
    return list(_CACHE.get("homes") or [])


def raw_of(scene_id):
    for v in list_automations():
        if v["scene_id"] == str(scene_id):
            return v
    return None


def public(v, with_raw=False):
    """去掉内部字段后给 HTTP 层。"""
    out = {k: x for k, x in v.items() if not k.startswith("_")}
    if with_raw:
        out["raw"] = v["_raw"]
    return out


EDIT_STYLE = "flat"   # 实测唯一被 Edit 接受的包装方式


def _validate_patch(patch):
    """写入前的字段级校验：防止把自动化改坏。"""
    if not isinstance(patch, dict):
        raise ValueError("patch 必须是对象")
    if not patch:
        # 空 patch 多半是「什么都没改就点了预览」：说清事实，别丢一个字段名给人猜
        raise ValueError("没有任何改动（patch 为空），没有需要写入的内容")
    bad = [k for k in patch if k not in EDITABLE]
    if bad:
        raise ValueError("不允许修改的字段：" + ", ".join(bad))
    if "name" in patch:
        name = patch["name"]
        if not isinstance(name, str) or not name.strip():
            raise ValueError("名称不能为空")
        if len(name.strip()) > 100:
            raise ValueError("名称过长（上限 100 字）")
        patch["name"] = name.strip()
    if "enable" in patch and not isinstance(patch["enable"], bool):
        raise ValueError("enable 必须是布尔值")
    for field, key in _BLOCK_KEY.items():
        if field not in patch:
            continue
        val = patch[field]
        if val is None or isinstance(val, str):
            continue
        if not isinstance(val, dict) or key not in val:
            raise ValueError(field + " 结构不合法，应含 " + key)
    return patch


def build_edit_payload(scene_id, patch=None, style=EDIT_STYLE):
    """只在本地构造 Edit payload，绝不发送。

    style 保留三种包装用于对照测试；默认 flat 是实测可用格式：
      flat     {...scene 33 字段..., "home_id":..., "owner_uid":...}  ← 服务端接受
      wrapped  {"scene_info": {...}, ...}                              ← 名称为空报错
      string   {"scene_info": "<JSON 字符串>", ...}                     ← 未验证
    """
    if style not in ("wrapped", "flat", "string"):
        raise ValueError("未知 payload 包装方式：" + str(style))
    v = raw_of(scene_id)
    if not v:
        raise KeyError("自动化不存在或列表未刷新：" + str(scene_id))
    patch = _validate_patch(dict(patch or {}))
    raw = copy.deepcopy(v["_raw"])
    changes = []
    for k, val in patch.items():
        before = raw.get(k)
        if before == val:
            continue
        changes.append({"field": k, "from": before, "to": val})
        raw[k] = val
    base = {"home_id": v["home_id"], "owner_uid": v["_owner_uid"]}
    payload = dict(base)
    if style == "flat":
        payload.update(raw)
    elif style == "string":
        payload["scene_info"] = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    else:
        payload["scene_info"] = raw
    return {
        "uri": _EDIT_URI,
        "operation": "edit",   # 与 create / delete 的 preview 同形，前端才能标出「修改」
        "scene_id": v["scene_id"],
        "home_id": v["home_id"],
        "home_name": v["home_name"],
        "name": v["name"],
        "style": style,
        "changes": changes,
        "payload": payload,
        "_scene": raw,   # 内部用：写入成功后局部更新缓存，不暴露给 HTTP 层
    }


def public_preview(p):
    """去掉内部字段，供 HTTP 层返回。"""
    return {k: v for k, v in p.items() if not k.startswith("_")}


def _refresh_local(scene_id, raw):
    """写入成功后就地更新缓存视图，避免 UI 还显示旧名称/旧状态。"""
    items = _CACHE.get("items") or []
    for i, v in enumerate(items):
        if v["scene_id"] != str(scene_id):
            continue
        fresh = view_of(raw, v["home_name"])
        fresh["_raw"] = raw
        fresh["_owner_uid"] = v["_owner_uid"]
        items[i] = fresh
        return True
    return False


def apply_edit(scene_id, patch=None, style=EDIT_STYLE):
    """真实写入云端：只允许改白名单字段，成功后同步本地缓存。

    调用方（HTTP 层）必须已取得用户确认；本函数不自己做二次弹窗。
    """
    p = build_edit_payload(scene_id, patch, style)
    if not p["changes"]:
        raise ValueError("与云端内容一致，无需写入")
    if not S.get("service"):
        raise RuntimeError("未登录")
    resp = cloud.call(
        S["service"].miio_request(_EDIT_URI, p["payload"]),
        timeout=20, what="automation_edit")
    _refresh_local(p["scene_id"], p["_scene"])
    log.info("自动化写入 scene_id=%s home=%s changes=%s resp=%s",
             p["scene_id"], p["home_name"],
             json.dumps(p["changes"], ensure_ascii=False)[:600],
             json.dumps(resp, ensure_ascii=False, default=str)[:300])
    return {
        "preview": public_preview(p),
        "result": resp,
        "local_synced": True,
    }


# ---------------------------------------------------------------- 创建
def _clean_name(name):
    if not isinstance(name, str) or not name.strip():
        raise ValueError("名称不能为空")
    name = name.strip()
    if len(name) > 100:
        raise ValueError("名称过长（上限 100 字）")
    return name


def _normalize_blocks(raw):
    """结构块可能以 JSON 字符串返回，新建时统一成对象，避免云端判空触发。"""
    for field in _BLOCK_KEY:
        val = _as_dict(raw.get(field))
        raw[field] = val or {
            ("express" if "condition" in field or "trigger" in field else "mode"):
                (1 if "condition" in field or "trigger" in field else 0),
            _BLOCK_KEY[field]: [],
        }
    return raw


def build_create_payload(template_scene_id, name, enable=False):
    """本地构造「新建自动化」payload，绝不发送。

    新建不是独立 Create 路由，而是 Edit 不带 scene_id。凭空构造有效的
    trigger / action 需要设备 did/model/spec，用户界面无法填写，所以采用
    「复制现有自动化」：保留模板的触发、条件、动作与时间窗，只换名称与状态。
    """
    v = raw_of(template_scene_id)
    if not v:
        raise KeyError("模板自动化不存在或列表未刷新：" + str(template_scene_id))
    name = _clean_name(name)
    if not isinstance(enable, bool):
        raise ValueError("enable 必须是布尔值")

    raw = _normalize_blocks(copy.deepcopy(v["_raw"]))
    for k in _CREATE_DROP:
        raw.pop(k, None)
    raw.update({
        "name": name,
        "enable": enable,
        "enable_push": False,     # 新建默认不推送
        "common_use": False,
        "no_record_log": False,
        "temporary": False,       # true 会创建出列表查不到的幽灵条目
        "home_id": str(v["home_id"]),
        "uid": str(raw.get("uid") or v["_owner_uid"]),
    })
    trg = _as_dict(raw.get("scene_trigger")).get("triggers") or []
    act = _as_dict(raw.get("scene_action")).get("actions") or []
    if not trg or not act:
        raise ValueError("模板缺少有效触发或动作，云端会拒绝创建；请换一个模板")

    payload = dict(raw)
    payload["home_id"] = str(v["home_id"])
    payload["owner_uid"] = v["_owner_uid"]
    return {
        "uri": _EDIT_URI,
        "style": EDIT_STYLE,
        "operation": "create",
        "scene_id": None,
        "template_scene_id": v["scene_id"],
        "template_name": v["name"],
        "home_id": v["home_id"],
        "home_name": v["home_name"],
        "name": name,
        "enable": enable,
        "changes": [
            {"field": "name", "from": v["name"], "to": name},
            {"field": "enable", "from": bool(v["_raw"].get("enable")), "to": enable},
        ],
        "payload": payload,
    }


def _invalidate_cache():
    """写入后让下次读取强制回云端；保留 items 以便拉取失败时仍有兜底。"""
    _CACHE["ts"] = 0.0


def _drop_local(scene_id):
    items = _CACHE.get("items")
    if not items:
        return False
    n = len(items)
    _CACHE["items"] = [v for v in items if v["scene_id"] != str(scene_id)]
    return len(_CACHE["items"]) != n


def apply_create(template_scene_id, name, enable=False):
    """真实新建一条云端自动化。调用方（HTTP 层）必须已取得用户确认。"""
    p = build_create_payload(template_scene_id, name, enable)
    if not S.get("service"):
        raise RuntimeError("未登录")
    resp = cloud.call(
        S["service"].miio_request(_EDIT_URI, p["payload"]),
        timeout=20, what="automation_create")
    created_id = str((resp or {}).get("scene_id") or "") if isinstance(resp, dict) else ""
    _invalidate_cache()
    log.info("自动化新建 template=%s home=%s name=%s enable=%s resp=%s",
             p["template_scene_id"], p["home_name"], p["name"], p["enable"],
             json.dumps(resp, ensure_ascii=False, default=str)[:300])
    return {
        "preview": public_preview(p),
        "result": resp,
        "created_id": created_id or None,
    }


# ---------------------------------------------------------------- 删除
def build_delete_payload(scene_id, name):
    """本地构造删除 payload。名称必须与云端当前名称完全一致，防止误删。"""
    v = raw_of(scene_id)
    if not v:
        raise KeyError("自动化不存在或列表未刷新：" + str(scene_id))
    if not isinstance(name, str) or name != v["name"]:
        raise ValueError("名称复核不一致，拒绝删除；请完整输入自动化名称")
    payload = {
        "scene_id": v["scene_id"],
        "home_id": v["home_id"],
        "owner_uid": v["_owner_uid"],
        "app_version": 12,
        "scene_type": 1,
    }
    return {
        "uri": _DELETE_URI,
        "operation": "delete",
        "scene_id": v["scene_id"],
        "home_id": v["home_id"],
        "home_name": v["home_name"],
        "name": v["name"],
        "enable": v["enable"],
        "changes": [{"field": "deleted", "from": v["name"], "to": None}],
        "payload": payload,
    }


def apply_delete(scene_id, name):
    """真实删除云端自动化，不可逆。调用方必须已取得用户逐条确认与名称复核。"""
    p = build_delete_payload(scene_id, name)
    if not S.get("service"):
        raise RuntimeError("未登录")
    resp = cloud.call(
        S["service"].miio_request(_DELETE_URI, p["payload"]),
        timeout=20, what="automation_delete")
    _drop_local(p["scene_id"])
    _invalidate_cache()
    log.warning("自动化删除 scene_id=%s home=%s name=%s resp=%s",
                p["scene_id"], p["home_name"], p["name"],
                json.dumps(resp, ensure_ascii=False, default=str)[:200])
    return {
        "preview": public_preview(p),
        "result": resp,
        "deleted": True,
    }
