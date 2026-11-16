"""③ 历史采样回归：SQLite 落盘、节流、降采样、清理、查询接口。"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp(prefix="mijia-history-")
os.environ["MIHOME_DATA_DIR"] = tmp

import app as appmod  # noqa: E402
import config  # noqa: E402
from services import history as hist  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


T = time.time()


def reset():
    hist._last.clear()
    hist._last_cleanup = 0.0


# ---------------------------------------------------------------- 写入过滤
reset()
live = {
    "d1": {"temperature": 18.1, "humidity": 64, "on": True,
           "mode": 3, "brightness": 70, "temperature_str": "18",
           "battery_level": float("nan"), "voltage": float("inf")},
    "d2": {"temperature": 21.5, "on": False},
}
ok(hist.record(live, now=T) == 3, "只写白名单数值读数（开关/枚举/脏值全部过滤）")
ok(len(hist.query(did="d1", hours=1, now=T)["d1"]) == 2, "d1 落盘温湿度两条曲线")
ok(hist.record(live, now=T + 10) == 0, "同 5 分钟窗口内不重复写")
ok(hist.record(live, now=T + 301) == 3, "超过采样间隔后再次写入")
q6 = hist.query(hours=1, now=T + 301)
ok(sum(len(pts) for ks in q6.values() for pts in ks.values()) == 6,
   "累计 6 个点（3 个键各 2 次采样）")

# ---------------------------------------------------------------- 查询与降采样
q = hist.query(did="d1", hours=24, now=T + 301)
ok(set(q.keys()) == {"d1"}, "按 did 过滤")
ok("temperature" in q["d1"] and "humidity" in q["d1"], "返回该设备的多条曲线")
ok(all(len(pts) >= 2 for pts in q["d1"].values()), "每个键都有时间点")
ok(hist.query(did="nobody", hours=24, now=T + 301) == {}, "不存在的设备返回空")
ok(hist.query(hours=0.1, now=T + 301, keys=["temperature"]).get("d1", {}).get("humidity") is None,
   "keys 参数只返回指定读数")
ok("d1" in hist.query(hours=24, now=T + 301), "不带 did 时批量返回全部设备")
ok(hist.query(hours=24, now=T + 8 * 86400) == {}, "超出保留窗口查不到旧数据")

# 降采样：一个键写 120 个点，查询压到 10 点以内
reset()
many = [hist.record({"dx": {"power": i * 1.0}}, now=T + i * 60, interval=0)
        for i in range(120)]
ok(sum(many) == 120, "连续 120 次采样全部写入")
pts = hist.query(did="dx", hours=24, max_points=10, now=T + 120 * 60)["dx"]["power"]
ok(2 <= len(pts) <= 10, "降采样后点数不超过上限")
ok(all(len(p) == 2 and isinstance(p[1], (int, float)) for p in pts), "点格式 [ts, value]")
ok(all(pts[i][0] <= pts[i + 1][0] for i in range(len(pts) - 1)), "点按时间正序")
ok(len(hist.query(did="dx", hours=24, max_points=500,
                  now=T + 120 * 60)["dx"]["power"]) == 120, "上限充足时保留全部点")

# ---------------------------------------------------------------- 过期清理
reset()
hist.record({"old": {"temperature": 10}}, now=T, interval=0)
ok("old" in hist.query(hours=1, now=T), "清理前旧点存在")
hist._last_cleanup = 0.0
hist.record({"new": {"temperature": 20}}, now=T + 8 * 86400, interval=0)
ok(hist.query(did="old", hours=168, now=T + 8 * 86400) == {},
   "7 天前的点在下次写入时被清理")
ok("new" in hist.query(hours=1, now=T + 8 * 86400), "新点保留")

# ---------------------------------------------------------------- HTTP 接口
reset()
hist.record({"api1": {"temperature": 22.5}, "api1b": {"humidity": 50}}, now=T, interval=0)
hist.record({"api1": {"temperature": 23.0}}, now=T + 301, interval=0)
fa = appmod.create_app()
fa.config["TESTING"] = True
c = fa.test_client()
r = c.get("/api/history?did=api1&hours=24&points=50")
ok(r.status_code == 200, "接口返回 200")
j = r.get_json()
ok(j["ok"] is True and j["did"] == "api1", "接口返回 did 与 ok")
ok("api1" in j["series"] and "api1b" not in j["series"], "接口按 did 过滤")
ok(len(j["series"]["api1"]["temperature"]) == 2, "接口返回两个采样点")
ok(c.get("/api/history?hours=abc").status_code == 400, "非法参数返回 400")
r2 = c.get("/api/history?hours=24&keys=temperature&points=50")
ok(all("humidity" not in ks for ks in r2.get_json()["series"].values()),
   "keys 参数在接口层生效")
ok(os.path.exists(config.HISTORY_DB_PATH), "历史库落在数据目录")

print("history_test: %d 项通过" % ok_n[0])
