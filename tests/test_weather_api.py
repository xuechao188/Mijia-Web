"""④ 天气接口回归：逐时/今日解析、WMO 映射、缓存与失败回退、city 查询参数。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["MIHOME_DATA_DIR"] = tempfile.mkdtemp(prefix="mijia-weather-test-")

from flask import Flask  # noqa: E402
from routes import misc  # noqa: E402
from services import weather as W  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


# ---------------------------------------------------------------- 时间工具
ok(W._hhmm("2026-11-13T06:32") == "06:32", "ISO 时间取 HH:MM")
ok(W._hhmm(None) is None, "空时间返回 None")
ok(W._hhmm("bogus") is None, "异常时间格式返回 None，不输出乱码")
ok(W._hhmm("2026-11-13T6:3") is None, "缺位时间返回 None")

# ---------------------------------------------------------------- 逐时解析
times = ["2026-11-13T%02d:00" % h for h in range(24)] + \
        ["2026-11-14T%02d:00" % h for h in range(24)]
raw = {
    "hourly": {
        "time": times,
        "temperature_2m": list(range(48)),
        "precipitation_probability": [10] * 48,
        "weather_code": [2] * 48,
    },
    "daily": {
        "temperature_2m_max": [21.4], "temperature_2m_min": [11.2],
        "sunrise": ["2026-11-13T06:32"], "sunset": ["2026-11-13T17:20"],
        "precipitation_probability_max": [30],
    },
}
h = W._parse_hourly(raw, "2026-11-13T10:45")
ok(len(h) == 24, "逐时预报截 24 条")
ok(h[0]["time"] == "10:00" and h[0]["temp"] == 10, "从当前小时起算")
ok(h[-1]["time"] == "09:00" and h[-1]["temp"] == 33, "跨日到次日")
ok(h[0] == {"time": "10:00", "temp": 10, "pop": 10, "code": 2}, "逐时字段完整")
ok(len(W._parse_hourly(raw, "2026-11-12T10:45")) == 24,
   "日期对不上时按小时回退，不从凌晨开始")
ok(len(W._parse_hourly({"hourly": {}}, "2026-11-13T10:45")) == 0,
   "缺逐时数据返回空表")
short = {"hourly": {"time": times[:12], "temperature_2m": list(range(12))}}
ok(len(W._parse_hourly(short, "2026-11-13T10:45")) == 2,
   "数据不足时只返回剩余条数，不越界")

d = W._parse_daily(raw)
ok(d["tmax"] == 21.4 and d["tmin"] == 11.2, "今日最高最低温")
ok(d["sunrise"] == "06:32" and d["sunset"] == "17:20", "日出日落取 HH:MM")
ok(d["pop_max"] == 30, "最大降水概率")
ok(W._parse_daily({})["tmax"] is None, "缺今日数据不崩")

# ---------------------------------------------------------------- 完整数据组装
FORECAST = {
    "current": {
        "time": "2026-11-13T10:45", "temperature_2m": 18.4,
        "apparent_temperature": 17.2, "weather_code": 61,
        "wind_speed_10m": 9.1, "relative_humidity_2m": 63, "is_day": 1,
    },
    "hourly": {
        "time": ["2026-11-13T10:00", "2026-11-13T11:00"],
        "temperature_2m": [18, 19], "precipitation_probability": [0, 20],
        "weather_code": [61, 61],
    },
    "daily": {
        "temperature_2m_max": [21], "temperature_2m_min": [11],
        "sunrise": ["2026-11-13T06:32"], "sunset": ["2026-11-13T17:20"],
        "precipitation_probability_max": [30],
    },
}
GEO = {"results": [{"name": "合肥", "latitude": 31.82, "longitude": 117.23}]}
AQI = {"current": {"european_aqi": 35}}


def fake_get_json(url, timeout=None):
    if "geocoding-api" in url:
        return GEO
    if "air-quality-api" in url:
        return AQI
    return FORECAST


orig_get = W._get_json
W._get_json = fake_get_json
try:
    w = W._load("合肥")
finally:
    W._get_json = orig_get

ok(w["city"] == "合肥" and w["temp"] == 18.4, "旧字段 city/temp 保持不变")
ok(w["text"] == "小雨" and w["code"] == 61, "WMO 天气码转中文")
ok(w["feels"] == 17.2 and w["wind"] == 9.1, "体感与风速不变")
ok(w["aqi"] == 35 and w["humidity"] == 63, "空气质量与湿度")
ok(w["is_day"] == 1 and w["updated"] == "10:45", "昼夜标记与更新时间")
ok(len(w["hourly"]) == 2 and w["hourly"][0]["time"] == "10:00", "逐时预报")
ok(w["today"]["tmax"] == 21 and w["today"]["sunrise"] == "06:32", "今日数据")
ok(w["stale"] is False, "新鲜数据不标 stale")


def aqi_fails(url, timeout=None):
    if "air-quality-api" in url:
        raise OSError("aqi down")
    return fake_get_json(url, timeout)


W._get_json = aqi_fails
try:
    w2 = W._load("合肥")
finally:
    W._get_json = orig_get
ok(w2["aqi"] is None and w2["temp"] == 18.4,
   "AQI 接口失败不影响其它天气字段")

# ---------------------------------------------------------------- 单次网络抖动重试
class FakeResp:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return b'{"ok": 1}'


attempts = []
orig_urlopen = W.urllib.request.urlopen


def flaky_urlopen(req, timeout=None):
    attempts.append(1)
    if len(attempts) == 1:
        raise OSError("ssl handshake timeout")
    return FakeResp()


W.urllib.request.urlopen = flaky_urlopen
try:
    got = W._get_json("https://example.test", timeout=2)
finally:
    W.urllib.request.urlopen = orig_urlopen
ok(got == {"ok": 1} and len(attempts) == 2,
   "单次 SSL 握手超时自动重试一次并成功")

W.urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(OSError("down"))
try:
    W._get_json("https://example.test", timeout=2)
    ok(False, "重试仍失败时应抛出异常")
except OSError:
    ok(True, "重试仍失败时抛出异常，不吞错")
finally:
    W.urllib.request.urlopen = orig_urlopen

# ---------------------------------------------------------------- 缓存 / 回退
W._CACHE.clear()
calls = []
DATA = {"city": "合肥", "temp": 18, "stale": False}


def fake_load_ok(city):
    calls.append(city)
    return dict(DATA)


orig_load = W._load
W._load = fake_load_ok
try:
    a = W.fetch("合肥")
    b = W.fetch("合肥")
    ok(len(calls) == 1, "10 分钟内重复请求命中缓存，不外呼")
    ok(a["temp"] == 18 and b["temp"] == 18, "缓存返回完整数据")

    W._CACHE["合肥"]["ts"] -= 700  # 模拟缓存过期

    def fake_load_fail(city):
        raise OSError("offline")

    W._load = fake_load_fail
    stale = W.fetch("合肥")
    ok(stale["temp"] == 18 and stale["stale"] is True,
       "外部接口失败时回退上次数据并标记 stale")
    ok(DATA["stale"] is False, "stale 是副本标记，不污染缓存原对象")

    W._CACHE.clear()
    W.fetch("合肥")  # 失败且无历史数据
    before = len(calls)
    W._load = fake_load_ok
    W.fetch("合肥")
    W.fetch("合肥")
    ok(len(calls) - before == 0, "失败后负缓存生效，不反复外呼")

    W._CACHE.clear()
    W._load = fake_load_fail
    W.fetch("合肥")
    W._CACHE["合肥"]["ts"] -= 30   # 失败后 30 秒
    W._load = fake_load_ok
    ok(W.fetch("合肥") is None, "失败后 30 秒内保持负缓存，不刷屏外呼")
    W._CACHE["合肥"]["ts"] -= 35   # 累计 65 秒，超过失败缓存窗口
    recovered = W.fetch("合肥")
    ok(recovered is not None and recovered["temp"] == 18,
       "失败 60 秒后自动重试并恢复，不必等 10 分钟")
finally:
    W._load = orig_load
    W._CACHE.clear()

# ---------------------------------------------------------------- HTTP 层
seen = []


def fake_fetch(city=None):
    seen.append(city)
    return {"city": city or "默认", "temp": 20, "text": "晴"}


orig_fetch = misc.weather.fetch
misc.weather.fetch = fake_fetch
try:
    fa = Flask(__name__)
    fa.register_blueprint(misc.bp)
    c = fa.test_client()
    r = c.get("/api/weather")
    ok(r.status_code == 200 and r.get_json()["ok"] is True, "默认天气接口 200")
    ok(r.get_json()["weather"]["temp"] == 20, "返回天气数据")
    ok(seen[-1] is None, "不传 city 时用服务器默认城市")

    r = c.get("/api/weather?city=%E5%8C%97%E4%BA%AC")
    ok(r.get_json()["weather"]["city"] == "北京", "支持城市查询参数")
    ok(seen[-1] == "北京", "city 参数透传到服务层")

    r = c.get("/api/weather?city=%20%20")
    ok(seen[-1] is None, "空白 city 归一化为默认城市")

    misc.weather.fetch = lambda city=None: None
    r = c.get("/api/weather")
    ok(r.get_json()["ok"] is False and r.get_json()["weather"] is None,
       "天气彻底失败时接口不报错，返回 ok=false")
finally:
    misc.weather.fetch = orig_fetch

print("weather_api_test: %d 项通过" % ok_n[0])
