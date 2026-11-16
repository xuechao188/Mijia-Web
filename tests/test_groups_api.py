"""分组后端回归：自定义分组 CRUD/容错/持久化、云端房间映射、API 与同源守卫。"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp(prefix="mijia-groups-")
os.environ["MIHOME_DATA_DIR"] = tmp

import config  # noqa: E402
from services import devices as dev  # noqa: E402
from services import groups as grp  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


# ---------------------------------------------------------------- 容错
ok(grp.load()["custom"] == [], "无文件时返回空分组")
with open(config.GROUPS_PATH, "w", encoding="utf-8") as f:
    f.write("{坏掉的 json")
ok(grp.load()["custom"] == [], "坏 JSON 当空分组")
with open(config.GROUPS_PATH, "w", encoding="utf-8") as f:
    json.dump({"version": 999, "custom": [{"id": "x", "name": "旧"}]}, f)
ok(grp.load()["custom"] == [], "版本不符一律作废")
os.remove(config.GROUPS_PATH)

# ---------------------------------------------------------------- CRUD
ok(grp.apply("create", {"name": ""})[0] is False, "空分组名被拒")
ok(grp.apply("bogus", {})[0] is False, "未知操作被拒")
created, gs, _ = grp.apply("create", {"name": "常用"})
ok(created and len(gs) == 1 and gs[0]["name"] == "常用", "新建分组成功")
gid = gs[0]["id"]
ok(grp.apply("create", {"name": "常用"})[0] is False, "同名分组被拒")
ok(grp.apply("add", {"id": gid, "did": "123"})[0] is True, "加入设备")
ok(grp.apply("add", {"id": gid, "did": "123"})[0] is True, "重复加入不报错")
ok(len(grp.list_groups()[0]["dids"]) == 1, "成员去重")
ok(grp.apply("add", {"id": gid, "did": 456})[0] is True
   and "456" in grp.list_groups()[0]["dids"], "数字 did 归一为字符串")
ok(grp.apply("add", {"id": "不存在", "did": "1"})[0] is False,
   "对不存在的分组操作被拒")
ok(grp.apply("rename", {"id": gid, "name": "每天用"})[0] is True
   and grp.list_groups()[0]["name"] == "每天用", "重命名生效")
ok(grp.apply("remove", {"id": gid, "did": "123"})[0] is True
   and grp.list_groups()[0]["dids"] == ["456"], "移出成员生效")
ok(len(grp.load()["custom"]) == 1, "写入已持久化到磁盘")

# ---------------------------------------------------------------- 房间映射
homes = [
    {"id": 101, "name": "信地", "rooms": [
        {"id": 1, "name": "卧室", "dids": ["78475274"]},
        {"id": 2, "name": "厨房", "dids": ["1092804866.s3", "blt.3.abc", "lumi.xyz"]},
    ]},
    {"id": 202, "name": "西山银杏", "rooms": [
        {"id": 3, "name": "厨房", "dids": ["242146894"]},
    ]},
]
loc = dev._rooms_from_homes(homes)
ok(loc["78475274"][0] == "101" and loc["78475274"][1] == "信地"
   and loc["78475274"][3] == "卧室", "设备带上家庭 id/名与房间名")
ok("1092804866" in loc and loc["1092804866"][3] == "厨房",
   "多键开关后缀 .s3 归一化到主 did")
ok("blt.3.abc" in loc and "lumi.xyz" in loc,
   "blt./lumi. 形式的真实 did 不被误截断")
ok(loc["242146894"][1] == "西山银杏" and loc["242146894"][3] == "厨房",
   "另一家庭同名厨房保留自己的归属")
ok(dev._rooms_from_homes([]) == {} and dev._rooms_from_homes(None) == {},
   "空家庭列表返回空映射")

devs = [{"did": "78475274"}, {"did": "1092804866"}, {"did": "999"}]
dev.apply_room_loc(devs, loc)
ok(devs[0]["home"] == "信地" and devs[0]["room"] == "卧室"
   and devs[0]["room_id"] == "1", "已知设备补齐四级归属")
ok(devs[1]["home"] == "信地" and devs[1]["room"] == "厨房",
   "后缀归一化后的主 did 也能匹配")
ok(devs[2]["home"] == "" and devs[2]["room"] == "",
   "云端没有归属的设备字段清空")
v = dev.build_device_view({"did": "1", "name": "x", "model": "x.y",
                           "home": "信地", "home_id": "101",
                           "room": "卧室", "room_id": "1"}, {})
ok(v["home"] == "信地" and v["room"] == "卧室" and v["room_id"] == "1",
   "设备视图把家庭/房间透给前端")

# ---------------------------------------------------------------- API
from app import create_app  # noqa: E402

client = create_app().test_client()
r = client.get("/api/groups")
ok(r.status_code == 200 and r.get_json()["ok"] is True, "GET /api/groups 可用")
ok(any(g["name"] == "每天用" for g in r.get_json()["groups"]),
   "GET 返回已持久化的分组")
r = client.post("/api/groups", json={"action": "create", "name": "临时分组"})
ok(r.status_code == 200 and r.get_json()["ok"] is True, "POST 新建分组")
new_id = next(g["id"] for g in r.get_json()["groups"]
              if g["name"] == "临时分组")
r = client.post("/api/groups", json={"action": "add", "id": new_id, "did": "777"})
ok(r.status_code == 200 and "777" in next(
    g["dids"] for g in r.get_json()["groups"] if g["id"] == new_id),
   "POST 加成员并回传最新分组")
ok(client.post("/api/groups", json={"action": "bogus"}).status_code == 400,
   "非法操作返回 400")
ok(client.post("/api/groups", json={"action": "create", "name": ""}).status_code == 400,
   "空名称返回 400")
ok(client.post("/api/groups", json={"action": "create", "name": "越权"},
               headers={"Origin": "https://evil.example"}).status_code == 403,
   "跨源写入被同源守卫拒绝")
ok(client.post("/api/groups", json={"action": "delete", "id": new_id})
   .status_code == 200, "POST 删除分组")
ok(all(g["id"] != new_id for g in client.get("/api/groups").get_json()["groups"]),
   "删除后不再返回")

print("groups_api_test: %d 项通过" % ok_n[0])
