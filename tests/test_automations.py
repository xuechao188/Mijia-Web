"""⑤ 自动化回归：结构解析、中文摘要、payload 构造、写入守卫、HTTP 只读/写入路由。

云端写入一律打桩，测试本身绝不向米家发任何请求。
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from flask import Flask  # noqa: E402
from routes import automations as api  # noqa: E402
from services import automations as A  # noqa: E402
from services import cloud  # noqa: E402
from services.state import S  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


# 与 GetSceneList 真实返回同构的精简样本（信地「卫生间 2分钟无人移动-关灯」）
RAW = {
    "scene_id": "1965783950534266880",
    "name": "卫生间 2分钟无人移动-Yeelight智能浴霸 关灯",
    "home_id": "100000000001",
    "uid": "1000001",
    "enable": True,
    "type": 0,
    "create_time": "1757514391",
    "update_time": "1764686101",
    "scene_trigger": {"express": 1, "triggers": [
        {"id": 1, "key": "event.no_motion", "name": "10分钟无人移动",
         "value_json": 600,
         "extra_json": {"device_name": "Aqara人体传感器",
                        "did": "lumi.158d0001e5fe77",
                        "model": "lumi.sensor_motion.aq2"}},
        {"id": 2, "key": "prop.onseat_state", "name": "空闲",
         "value_json": "off",
         "extra_json": {"device_name": "马桶盖", "did": "317422772"}},
    ]},
    "scene_condition": {"express": 0, "conditions": [
        {"id": 1, "key": "prop.humidity", "name": "湿度高于90%",
         "value_json": 90, "extra_json": {"device_name": "温湿度计"}},
    ]},
    "scene_action": {"mode": 0, "actions": [
        {"id": 1, "name": "关灯",
         "payload_json": {"command": "set_power", "device_name": "浴霸",
                          "did": "306829130", "model": "yeelink.bhf_light.v2",
                          "value": ["off"]}},
    ]},
    "scene_else_action": {"mode": 0, "actions": []},
    "timewindow": {"from": "0 0 0 * * 0,1,2 *", "to": "0 0 0 * * * *"},
}

# ---------------------------------------------------------------- 结构解析
v = A.view_of(RAW, "信地")
ok(v["scene_id"] == "1965783950534266880", "场景 id 原样保留")
ok(v["home_name"] == "信地" and v["home_id"] == "100000000001", "家庭信息")
ok(v["enable"] is True and v["type"] == 0, "启停位与子类型")
ok(v["counts"] == {"trigger": 2, "condition": 1, "action": 1, "else": 0},
   "触发/条件/动作计数")
ok(v["triggers"][0]["device"] == "Aqara人体传感器", "触发设备名来自 extra_json")
ok(v["triggers"][0]["did"] == "lumi.158d0001e5fe77", "触发设备 did")
ok(v["triggers"][0]["value"] == 600, "触发阈值 value_json")
ok(v["actions"][0]["device"] == "浴霸", "动作设备名来自 payload_json")
ok(" 或 " in v["trigger_text"], "express=1 的多个触发用「或」连接")
ok("Aqara人体传感器 10分钟无人移动" in v["trigger_text"], "触发文案")
ok("温湿度计 湿度高于90%" in v["condition_text"], "条件文案")
ok(v["action_text"] == "浴霸 关灯", "动作文案")
ok(v["summary"].startswith("当 ") and "，且 " in v["summary"]
   and "，执行 " in v["summary"], "中文摘要「当…且…执行…」")
ok("否则" not in v["summary"], "无 else 动作时不显示「否则」")

empty = A.view_of({"scene_id": "x", "name": "空自动化"}, "信地")
ok(empty["counts"]["trigger"] == 0 and empty["summary"] == "空自动化",
   "缺字段时用名称兜底，不抛异常")
ok(A.view_of({"scene_id": "x", "scene_trigger": '{"triggers": []}'})["counts"]["trigger"] == 0,
   "字符串化 JSON 块也能解析")
ok(A._as_dict("not-json") == {}, "非法字符串块返回空对象")

# ---------------------------------------------------------------- 对外视图
v["_raw"] = RAW
v["_owner_uid"] = 1000001
pub = A.public(v)
ok("_raw" not in pub and "_owner_uid" not in pub, "列表接口不泄漏内部字段")
ok("raw" not in pub, "列表接口不夹带原始大对象")
ok("raw" in A.public(v, with_raw=True), "详情接口单独给原始数据")

# ---------------------------------------------------------------- payload 构造
CACHE0 = {"ts": 9999999999.0, "items": [v],
          "homes": [{"id": "100000000001", "name": "信地"}]}
A._CACHE.update(CACHE0)

p = A.build_edit_payload(v["scene_id"], {"name": "新名字", "enable": False})
ok(p["uri"].endswith("/AppSceneService/Edit"), "目标为 Edit 接口")
ok(p["style"] == "flat", "默认使用实测可用的 flat 包装")
ok(p["operation"] == "edit", "修改预览带 operation，前端能标出「修改」")
ok(p["changes"] == [{"field": "name", "from": RAW["name"], "to": "新名字"},
                    {"field": "enable", "from": True, "to": False}]
   or len(p["changes"]) == 2, "记录改动前后值供确认")
ok(p["payload"]["name"] == "新名字", "flat 把名称放在顶层")
ok(p["payload"]["enable"] is False, "flat 把启停位放在顶层")
ok(p["payload"]["scene_id"] == RAW["scene_id"], "身份字段不变")
ok("scene_info" not in p["payload"], "flat 不带 scene_info（该包装会被云端判名称为空）")
ok(RAW["name"] == "卫生间 2分钟无人移动-Yeelight智能浴霸 关灯",
   "构造 payload 用深拷贝，不污染原始缓存对象")
ok(p["payload"]["home_id"] == "100000000001" and p["payload"]["owner_uid"] == 1000001,
   "附带家庭与归属 uid")
ok("_scene" in p and "_scene" not in A.public_preview(p),
   "内部 scene 对象不暴露给 HTTP 层")

wrapped = A.build_edit_payload(v["scene_id"], {"name": "新名字"}, "wrapped")
ok(wrapped["payload"]["scene_info"]["name"] == "新名字",
   "wrapped 包装仍可本地生成（仅用于对照测试）")
ok("scene_info" not in wrapped["payload"] or wrapped["payload"]["scene_info"]["scene_id"] == RAW["scene_id"],
   "wrapped 保留身份字段")
flat = A.build_edit_payload(v["scene_id"], {"name": "平铺"}, "flat")
ok(flat["payload"]["scene_id"] == RAW["scene_id"] and "scene_info" not in flat["payload"],
   "flat 包装把字段平铺到顶层")
string = A.build_edit_payload(v["scene_id"], {"name": "字符串"}, "string")
ok(isinstance(string["payload"]["scene_info"], str), "string 包装把 scene_info 序列化")
ok("新名字" not in string["payload"]["scene_info"], "不同 style 互不影响")

no_change = A.build_edit_payload(v["scene_id"], {"name": RAW["name"]})
ok(no_change["changes"] == [], "等值回写不产生改动项（可作为无副作用写入测试）")

# ---------------------------------------------------------------- 字段校验
for bad_patch, label in [
    ({}, "空 patch"),
    (None, "None patch"),
    ({"scene_id": "hacked"}, "身份字段"),
    ({"name": "   "}, "空白名称"),
    ({"name": 123}, "非字符串名称"),
    ({"name": "x" * 101}, "超长名称"),
    ({"enable": "false"}, "非布尔 enable"),
    ({"scene_trigger": {"foo": []}}, "缺 triggers 的结构块"),
]:
    try:
        A.build_edit_payload(v["scene_id"], bad_patch)
        ok(False, "应拒绝：" + label)
    except (ValueError, KeyError) as e:
        ok(True, "拒绝对云端有害的 patch：" + label)
        if label in ("空 patch", "None patch"):
            ok("没有任何改动" in str(e), "空改动给出看得懂的提示：" + str(e))

try:
    A.build_edit_payload(v["scene_id"], {"name": "x"}, "unknown")
    ok(False, "非法包装方式应报错")
except ValueError:
    ok(True, "非法包装方式被拒绝")
try:
    A.build_edit_payload("not-exist", {"name": "x"})
    ok(False, "不存在的场景应报错")
except KeyError:
    ok(True, "不存在的场景报错，不构造 payload")
ok(A.build_edit_payload(v["scene_id"], {"name": "  去空格  "})["payload"]["name"] == "去空格",
   "名称自动去首尾空格")

# ---------------------------------------------------------------- 写入服务（打桩）
sent = []
orig_call = cloud.call
orig_service = S.get("service")
orig_cache = copy.deepcopy(A._CACHE)


class FakeService:
    def miio_request(self, uri, data):
        return ("coro", uri, data)   # 普通对象：cloud.call 已打桩，不产生未 await 协程


def fake_call(coro, timeout=None, what=""):
    sent.append((coro, what))
    return {"scene_id": RAW["scene_id"], "activated": False, "trigger_order": 0}


cloud.call = fake_call
S["service"] = FakeService()
try:
    r = A.apply_edit(v["scene_id"], {"name": "写入测试", "enable": False})
    ok(len(sent) == 1, "apply_edit 恰好发出一次云端写请求")
    ok(sent[0][0][1].endswith("/AppSceneService/Edit"), "写请求打到 Edit 接口")
    ok(sent[0][1] == "automation_edit", "写请求走独立 what 标记便于排查")
    ok(sent[0][0][2]["name"] == "写入测试" and sent[0][0][2]["enable"] is False,
       "发出的是 flat payload，改动落在顶层")
    ok(r["result"]["scene_id"] == RAW["scene_id"] and r["local_synced"] is True,
       "返回云端结果并同步本地缓存")
    ok(A._CACHE["items"][0]["name"] == "写入测试" and A._CACHE["items"][0]["enable"] is False,
       "缓存视图即时更新，UI 不显示旧值")
    ok("_scene" not in r["preview"], "返回给 HTTP 层的 preview 不含内部字段")

    before = len(sent)
    try:
        A.apply_edit(v["scene_id"], {"name": "写入测试"})
        ok(False, "等值写入应被拒绝")
    except ValueError:
        ok(True, "等值写入不发请求，避免无意义改动")
    ok(len(sent) == before, "等值写入确实没有外呼")
    try:
        A.apply_edit(v["scene_id"], {"uid": "0"})
        ok(False, "身份字段应被拒绝")
    except ValueError:
        ok(True, "写入路径同样受白名单保护")
    ok(len(sent) == before, "非法写入没有外呼")

    def boom(coro, timeout=None, what=""):
        raise RuntimeError("cloud down")

    cloud.call = boom
    try:
        A.apply_edit(v["scene_id"], {"name": "不会生效"})
        ok(False, "云端异常应透传")
    except RuntimeError:
        ok(True, "云端异常透传，不伪装成成功")
finally:
    cloud.call = orig_call
    S["service"] = orig_service
    A._CACHE.clear()
    A._CACHE.update(orig_cache)

# ---------------------------------------------------------------- 创建 / 删除服务（打桩）
orig_cache2 = copy.deepcopy(A._CACHE)
orig_list2 = A.list_automations
# 本段只关心本地 payload 构造与打桩写入，列表一律读缓存，杜绝任何真实外呼
A.list_automations = lambda force=False, home_id=None: list(A._CACHE["items"] or [])
sent2 = []
cloud.call = None          # 下面每个用例单独打桩，避免误用上一次的桩
S["service"] = FakeService()
try:
    cp = A.build_create_payload(v["scene_id"], "  新建的自动化  ")
    pay = cp["payload"]
    ok(cp["uri"].endswith("/AppSceneService/Edit"), "新建复用 Edit 路由（无独立 Create）")
    ok(cp["operation"] == "create" and cp["scene_id"] is None, "preview 标记创建操作")
    ok("scene_id" not in pay, "新建 payload 绝不带 scene_id（带了会变成编辑）")
    ok("create_time" not in pay and "update_time" not in pay, "剔除模板时间戳")
    ok(pay["name"] == "新建的自动化", "新建名称去首尾空格")
    ok(pay["enable"] is False and pay["enable_push"] is False,
       "新建默认停用且不产生推送")
    ok(pay["temporary"] is False, "temporary=false，避免列表查不到的幽灵条目")
    ok(pay["no_record_log"] is False and pay["common_use"] is False,
       "不继承模板的临时与常用标记")
    ok(len(pay["scene_trigger"]["triggers"]) == 2
       and len(pay["scene_action"]["actions"]) == 1,
       "复制模板的触发与动作（凭空构造会被云端拒绝）")
    ok(pay["home_id"] == "100000000001" and pay["owner_uid"] == 1000001,
       "新建附带家庭与归属 uid")
    ok(cp["template_scene_id"] == v["scene_id"]
       and cp["template_name"] == RAW["name"], "preview 记录模板来源")
    ok(cp["changes"][0]["to"] == "新建的自动化", "preview 记录改动前后值")
    ok(A.public_preview(cp) == cp, "创建 preview 不含需要隐藏的内部字段")

    for fn, label in [
        (lambda: A.build_create_payload(v["scene_id"], ""), "空名称"),
        (lambda: A.build_create_payload(v["scene_id"], "   "), "空白名称"),
        (lambda: A.build_create_payload(v["scene_id"], 123), "非字符串名称"),
        (lambda: A.build_create_payload(v["scene_id"], "x" * 101), "超长名称"),
        (lambda: A.build_create_payload(v["scene_id"], "x", "false"), "enable 非布尔"),
        (lambda: A.build_create_payload("not-exist", "x"), "模板不存在"),
    ]:
        try:
            fn()
            ok(False, "应拒绝：" + label)
        except (ValueError, KeyError):
            ok(True, "拒绝有害创建：" + label)

    # 空触发 / 空动作的模板必须提前挡掉（云端会报 scene trigger not exist）
    empty_raw = {"scene_id": "empty", "name": "空模板", "home_id": "100000000001",
                 "scene_trigger": {"triggers": []},
                 "scene_action": {"actions": []}}
    empty_v = A.view_of(empty_raw, "信地")
    empty_v["_raw"] = empty_raw
    empty_v["_owner_uid"] = 1000001
    A._CACHE["items"] = list(A._CACHE["items"]) + [empty_v]
    try:
        A.build_create_payload("empty", "新")
        ok(False, "空触发模板应被拒绝")
    except ValueError:
        ok(True, "空触发/空动作模板提前拒绝，不发无效请求")

    # 字符串化的结构块要能还原成对象，否则云端同样判空触发
    str_raw = copy.deepcopy(RAW)
    str_raw["scene_id"] = "strblocks"
    str_raw["scene_trigger"] = json.dumps(str_raw["scene_trigger"], ensure_ascii=False)
    str_raw["scene_action"] = json.dumps(str_raw["scene_action"], ensure_ascii=False)
    str_v = A.view_of(str_raw, "信地")
    str_v["_raw"] = str_raw
    str_v["_owner_uid"] = 1000001
    A._CACHE["items"] = list(A._CACHE["items"]) + [str_v]
    sp = A.build_create_payload("strblocks", "字符串块")
    ok(isinstance(sp["payload"]["scene_trigger"], dict)
       and isinstance(sp["payload"]["scene_action"], dict),
       "字符串化的触发/动作块被规范化为对象")

    def fake_call2(coro, timeout=None, what=""):
        sent2.append((coro, what))
        return {"scene_id": "2121114743619997696", "activated": False}

    cloud.call = fake_call2
    A._CACHE["ts"] = 9999999999.0
    rc = A.apply_create(v["scene_id"], "新建成功")
    ok(len(sent2) == 1, "apply_create 恰好发出一次云端写请求")
    ok(sent2[0][0][1].endswith("/AppSceneService/Edit"), "新建请求打到 Edit")
    ok(sent2[0][1] == "automation_create", "新建走独立 what 标记便于排查")
    ok("scene_id" not in sent2[0][0][2], "实际发出的 payload 不含 scene_id")
    ok(rc["created_id"] == "2121114743619997696", "提取云端返回的新 scene_id")
    ok(A._CACHE["ts"] == 0.0, "新建后缓存失效，下次列表强制读云端")

    cloud.call = boom
    before = len(sent2)
    try:
        A.apply_create(v["scene_id"], "不会生效")
        ok(False, "新建失败应透传")
    except RuntimeError:
        ok(True, "新建云端异常透传，不伪装成功")
    ok(len(sent2) == before, "失败的新建没有额外外呼")

    # ---------------- 删除 payload 与写入
    dp = A.build_delete_payload(v["scene_id"], RAW["name"])
    ok(dp["uri"].endswith("/AppSceneService/Delete"), "删除走独立 Delete 路由")
    ok(dp["operation"] == "delete" and dp["scene_id"] == RAW["scene_id"],
       "preview 标记删除目标")
    ok(dp["payload"] == {
        "scene_id": RAW["scene_id"], "home_id": "100000000001",
        "owner_uid": 1000001, "app_version": 12, "scene_type": 1,
    }, "删除 payload 与 ④ 实测一致")
    for bad in ["", "模板", RAW["name"] + " ", RAW["name"][:-1], None]:
        try:
            A.build_delete_payload(v["scene_id"], bad)
            ok(False, "应拒绝复核名称 " + repr(bad))
        except ValueError:
            ok(True, "名称复核拒绝不精确匹配：" + repr(bad))
    try:
        A.build_delete_payload("not-exist", RAW["name"])
        ok(False, "不存在的 id 应拒绝")
    except KeyError:
        ok(True, "删除不存在的自动化被拒绝")

    def fake_del(coro, timeout=None, what=""):
        sent2.append((coro, what))
        return True

    cloud.call = fake_del
    A._CACHE["ts"] = 9999999999.0
    n_before = len(A._CACHE["items"])
    rd = A.apply_delete(v["scene_id"], RAW["name"])
    ok(sent2[-1][0][1].endswith("/AppSceneService/Delete"), "删除请求打到 Delete")
    ok(sent2[-1][1] == "automation_delete", "删除走独立 what 标记")
    ok(sent2[-1][0][2]["scene_id"] == RAW["scene_id"], "发出的 id 与复核目标一致")
    ok(rd["deleted"] is True, "返回删除结果")
    ok(len(A._CACHE["items"]) == n_before - 1, "缓存就地移除已删除条目")
    ok(A._CACHE["ts"] == 0.0, "删除后缓存失效，列表强制刷新")
    ok(A.raw_of(v["scene_id"]) is None, "本地已查不到被删除条目")

    cloud.call = boom
    before = len(sent2)
    try:
        A.apply_delete("empty", "空模板")
        ok(False, "删除失败应透传")
    except RuntimeError:
        ok(True, "删除云端异常透传，不伪装成功")
    ok(len(sent2) == before, "失败的删除没有额外外呼")
    ok(A.raw_of("empty") is not None, "删除失败不误删本地缓存")
finally:
    cloud.call = orig_call
    S["service"] = orig_service
    A.list_automations = orig_list2
    A._CACHE.clear()
    A._CACHE.update(orig_cache2)

# ---------------------------------------------------------------- HTTP 只读/写入
seen = []
orig_fetch = A.list_automations
orig_raw = A.raw_of
orig_apply = A.apply_edit


def fake_list(force=False, home_id=None):
    seen.append(("list", force, home_id))
    return [v]


def fake_apply(sid, patch, style):
    seen.append(("apply", sid, patch, style))
    return {"preview": {"changes": [{"field": "name", "from": "a", "to": "b"}]},
            "result": {"scene_id": sid}, "local_synced": True}


A.list_automations = fake_list
A.raw_of = lambda sid: v
A.apply_edit = fake_apply
try:
    fa = Flask(__name__)
    fa.register_blueprint(api.bp)
    c = fa.test_client()

    r = c.get("/api/automations")
    d = r.get_json()
    ok(r.status_code == 200 and d["ok"] is True, "列表接口 200")
    ok(d["count"] == 1 and d["enabled"] == 1, "返回数量与启用数")
    ok(d["writable"] is True, "Edit 已验证，前端开放改名与启停")
    ok(d["create_supported"] is True and d["delete_supported"] is True,
       "④ 闭环验证通过后，创建/删除标记为已开放")
    ok("_raw" not in d["automations"][0], "列表不含内部字段")
    ok(seen[-1][0] == "list" and seen[-1][1] is False, "默认不强制刷新")

    r = c.get("/api/automations?home_id=100000000001&force=1")
    ok(r.status_code == 200 and seen[-1] == ("list", True, "100000000001"),
       "home_id / force 参数透传")

    r = c.get("/api/automations/detail?scene_id=1965783950534266880")
    ok(r.get_json()["item"]["raw"]["scene_id"] == RAW["scene_id"], "详情含原始数据")
    r = c.get("/api/automations/detail")
    ok(r.status_code == 400, "详情缺 scene_id 返回 400")

    r = c.post("/api/automations/preview", json={"scene_id": v["scene_id"],
                                                 "patch": {"enable": False}})
    d = r.get_json()
    ok(r.status_code == 200 and d["sent"] is False, "preview 明确标注未发送")
    ok(d["preview"]["uri"].endswith("/Edit"), "preview 返回目标接口")
    ok(d["preview"]["style"] == "flat", "preview 默认展示实测可用的 flat 包装")
    r = c.post("/api/automations/preview", json={"scene_id": v["scene_id"],
                                                 "style": "bad"})
    ok(r.status_code == 400, "非法包装方式被拒绝")
    r = c.post("/api/automations/preview", json={})
    ok(r.status_code == 400, "缺 scene_id 被拒绝")

    # 写入路由：没有显式确认一律不发请求
    before = [x for x in seen if x[0] == "apply"]
    r = c.post("/api/automations/apply", json={"scene_id": v["scene_id"],
                                               "patch": {"name": "x"}})
    ok(r.status_code == 400 and r.get_json().get("sent") is not True,
       "apply 缺 confirm=true 被拒绝")
    r = c.post("/api/automations/apply", json={"scene_id": v["scene_id"],
                                               "patch": {"name": "x"},
                                               "confirm": "yes"})
    ok(r.status_code == 400, "confirm 必须是布尔 true，字符串不认")
    r = c.post("/api/automations/apply", json={"scene_id": v["scene_id"],
                                               "patch": {}, "confirm": True})
    ok(r.status_code == 400, "空 patch 被拒绝")
    r = c.post("/api/automations/apply", json={"patch": {"name": "x"},
                                               "confirm": True})
    ok(r.status_code == 400, "缺 scene_id 被拒绝")
    ok(len([x for x in seen if x[0] == "apply"]) == len(before),
       "所有非法请求都没有触发写入")

    r = c.post("/api/automations/apply", json={"scene_id": v["scene_id"],
                                               "patch": {"name": "改名完成"},
                                               "confirm": True})
    d = r.get_json()
    ok(r.status_code == 200 and d["ok"] is True and d["sent"] is True,
       "显式确认后 apply 成功并返回 sent=true")
    ok(seen[-1] == ("apply", v["scene_id"], {"name": "改名完成"}, A.EDIT_STYLE),
       "apply 透传 scene_id / patch，并固定使用实测可用包装")
    ok(d["result"]["scene_id"] == v["scene_id"], "返回云端写入结果")

    A.apply_edit = lambda sid, patch, style: (_ for _ in ()).throw(RuntimeError("cloud down"))
    r = c.post("/api/automations/apply", json={"scene_id": v["scene_id"],
                                               "patch": {"name": "x"}, "confirm": True})
    ok(r.status_code == 502 and r.get_json()["sent"] is False,
       "云端写入失败返回 502 且不伪装成功")
    A.apply_edit = fake_apply

    orig_create = A.apply_create
    orig_delete = A.apply_delete
    created, deleted = [], []

    def fake_create(sid, name, enable):
        created.append((sid, name, enable))
        return {"preview": {"operation": "create"},
                "result": {"scene_id": "new-1"}, "created_id": "new-1"}

    def fake_delete(sid, name):
        deleted.append((sid, name))
        return {"preview": {"operation": "delete"},
                "result": True, "deleted": True}

    A.apply_create = fake_create
    A.apply_delete = fake_delete
    try:
        r = c.post("/api/automations/create/preview", json={
            "template_scene_id": v["scene_id"], "name": "预览新建"})
        d = r.get_json()
        ok(r.status_code == 200 and d["sent"] is False, "创建预览明确标注未发送")
        ok(d["preview"]["uri"].endswith("/Edit")
           and "scene_id" not in d["preview"]["payload"],
           "创建预览是 Edit 且 payload 不含 scene_id")
        ok(d["preview"]["template_scene_id"] == v["scene_id"], "创建预览记录模板来源")
        r = c.post("/api/automations/create/preview", json={
            "template_scene_id": v["scene_id"], "name": " "})
        ok(r.status_code == 400, "创建预览拒绝空名称")
        r = c.post("/api/automations/create/preview", json={
            "template_scene_id": v["scene_id"], "name": "x", "enable": "false"})
        ok(r.status_code == 400, "enable 字符串不被强转成 true")

        r = c.post("/api/automations/create", json={
            "template_scene_id": v["scene_id"], "name": "新自动化"})
        ok(r.status_code == 400 and not created, "create 缺 confirm=true 被拒绝")
        r = c.post("/api/automations/create", json={
            "template_scene_id": v["scene_id"], "name": "x", "confirm": "yes"})
        ok(r.status_code == 400 and not created, "confirm 必须是布尔 true")
        r = c.post("/api/automations/create", json={
            "name": "x", "confirm": True})
        ok(r.status_code == 400 and not created, "create 缺模板 scene_id 被拒绝")
        r = c.post("/api/automations/create", json={
            "template_scene_id": v["scene_id"], "name": "x",
            "enable": 1, "confirm": True})
        ok(r.status_code == 400 and not created, "create 拒绝非布尔 enable")
        r = c.post("/api/automations/create", json={
            "template_scene_id": v["scene_id"], "name": "新自动化",
            "enable": False, "confirm": True})
        d = r.get_json()
        ok(r.status_code == 200 and d["sent"] is True and d["created_id"] == "new-1",
           "确认后创建成功并返回新 scene_id")
        ok(created == [(v["scene_id"], "新自动化", False)], "透传模板/名称/状态")
        A.apply_create = lambda sid, name, enable: (_ for _ in ()).throw(RuntimeError("cloud down"))
        r = c.post("/api/automations/create", json={
            "template_scene_id": v["scene_id"], "name": "x", "confirm": True})
        ok(r.status_code == 502 and r.get_json()["sent"] is False,
           "创建云端失败返回 502 且不伪装成功")
        A.apply_create = fake_create

        r = c.post("/api/automations/delete/preview", json={
            "scene_id": v["scene_id"], "name": RAW["name"]})
        d = r.get_json()
        ok(r.status_code == 200 and d["sent"] is False, "删除预览明确标注未发送")
        ok(d["preview"]["uri"].endswith("/Delete"), "删除预览指向 Delete")
        r = c.post("/api/automations/delete/preview", json={
            "scene_id": v["scene_id"], "name": RAW["name"][:-1]})
        ok(r.status_code == 400, "删除预览拒绝名称不一致")

        r = c.post("/api/automations/delete", json={
            "scene_id": v["scene_id"], "name": RAW["name"]})
        ok(r.status_code == 400 and not deleted, "delete 缺 confirm=true 被拒绝")
        r = c.post("/api/automations/delete", json={
            "scene_id": v["scene_id"], "confirm": True})
        ok(r.status_code == 400 and not deleted, "delete 缺复核名称被拒绝")
        r = c.post("/api/automations/delete", json={
            "scene_id": v["scene_id"], "name": RAW["name"] + " ",
            "confirm": True})
        ok(r.status_code == 400 and not deleted, "delete 名称带尾空格也被拒绝")
        r = c.post("/api/automations/delete", json={
            "scene_id": v["scene_id"], "name": RAW["name"], "confirm": True})
        d = r.get_json()
        ok(r.status_code == 200 and d["sent"] is True and d["deleted"] is True,
           "确认且名称复核通过后删除成功")
        ok(deleted == [(v["scene_id"], RAW["name"])], "删除只带复核过的 id 与名称")
        A.apply_delete = lambda sid, name: (_ for _ in ()).throw(RuntimeError("cloud down"))
        r = c.post("/api/automations/delete", json={
            "scene_id": v["scene_id"], "name": RAW["name"], "confirm": True})
        ok(r.status_code == 502 and r.get_json()["sent"] is False,
           "删除云端失败返回 502 且不伪装成功")
    finally:
        A.apply_create = orig_create
        A.apply_delete = orig_delete

    rules = {rule.rule for rule in fa.url_map.iter_rules()}
    for path in ("/api/automations/apply",
                 "/api/automations/create", "/api/automations/create/preview",
                 "/api/automations/delete", "/api/automations/delete/preview"):
        ok(path in rules, "写入/预览路由已注册：" + path)
finally:
    A.list_automations = orig_fetch
    A.raw_of = orig_raw
    A.apply_edit = orig_apply

print("automations_test: %d 项通过" % ok_n[0])
