"""天气数据：Open-Meteo 免费接口（无需 key、无需注册）。

④ 阶段把顶部通栏改成天气卡片，需要比原来更多的信息：
  - current：温度 / 体感 / 天气码 / 风速 / 湿度 / 昼夜
  - hourly：从当前小时起 24 条逐时预报（温度、降水概率、天气码）
  - daily：今日最高最低温、日出日落、最大降水概率
  - aqi：欧洲 AQI（可选，拿不到不影响其它字段）

兼容约定：city/temp/feels/code/text/wind/aqi 这些旧字段保持不变，
cli.py 与老前端都能继续用；新增字段一律是附加的。

缓存：按城市缓存 10 分钟。外部接口失败时，若曾成功过就返回上次数据并
标记 stale=True，卡片显示「数据未更新」而不是整块消失。
"""
import json
import time
import urllib.parse
import urllib.request

import config
import logx

log = logx.get("mihome.weather")

_WMO = {
    0: "晴", 1: "大部晴朗", 2: "多云", 3: "阴",
    45: "雾", 48: "冻雾", 51: "毛毛雨", 53: "毛毛雨", 55: "毛毛雨",
    61: "小雨", 63: "中雨", 65: "大雨", 66: "冻雨", 67: "冻雨",
    71: "小雪", 73: "中雪", 75: "大雪", 77: "雪粒",
    80: "阵雨", 81: "阵雨", 82: "强阵雨",
    85: "阵雪", 86: "阵雪", 95: "雷阵雨", 96: "雷暴伴冰雹", 99: "雷暴伴冰雹",
}

# city -> {"ts": monotonic, "data": 最新成功结果 or None, "last": 最近一次成功结果}
_CACHE = {}


def _get_json(url, timeout=None):
    req = urllib.request.Request(url, headers={"User-Agent": "Mijia-Web/0.1"})
    t = timeout or config.WEATHER_TIMEOUT_S
    # Open-Meteo 偶发 SSL 握手超时；只对单个请求立刻重试一次，
    # 不重跑整条 3 次外呼的链路，避免把一个接口故障放大成 48 秒阻塞
    for attempt in (0, 1):
        try:
            with urllib.request.urlopen(req, timeout=t) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception:
            if attempt == 1:
                raise


def _hhmm(v):
    """Open-Meteo 时间形如 2026-11-13T06:32，取 HH:MM；异常格式返回 None。"""
    if v is None:
        return None
    s = str(v).split("T")[-1][:5]
    if len(s) != 5 or s[2] != ":" or not (s[:2] + s[3:]).isdigit():
        return None
    return s


def _first(daily, key):
    arr = daily.get(key) or []
    return arr[0] if arr else None


def _parse_hourly(w, cur_time):
    """从当前小时起截 24 条逐时预报，保证大卡的曲线是「接下来」而不是「今天凌晨」。"""
    h = w.get("hourly") or {}
    times = h.get("time") or []
    temps = h.get("temperature_2m") or []
    pops = h.get("precipitation_probability") or []
    codes = h.get("weather_code") or []

    prefix = str(cur_time or "")[:13]  # YYYY-MM-DDTHH
    hour = str(cur_time or "")[11:13]
    start = 0
    if prefix:
        for i, t in enumerate(times):
            if str(t)[:13] == prefix:
                start = i
                break
        else:
            # 日期对不上（时区差异 / 接口时间格式变化）时退一步只比小时，
            # 否则曲线会从当天凌晨开始，看起来像「过去」而不是「接下来」
            for i, t in enumerate(times):
                if str(t)[11:13] == hour:
                    start = i
                    break

    out = []
    for i in range(start, min(start + 24, len(times))):
        out.append({
            "time": _hhmm(times[i]),
            "temp": temps[i] if i < len(temps) else None,
            "pop": pops[i] if i < len(pops) else None,
            "code": codes[i] if i < len(codes) else 0,
        })
    return out


def _parse_daily(w):
    d = w.get("daily") or {}
    return {
        "tmax": _first(d, "temperature_2m_max"),
        "tmin": _first(d, "temperature_2m_min"),
        "sunrise": _hhmm(_first(d, "sunrise")),
        "sunset": _hhmm(_first(d, "sunset")),
        "pop_max": _first(d, "precipitation_probability_max"),
    }


def _load(city):
    geo = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search?name=%s&count=1&language=zh"
        % urllib.parse.quote(city))
    hit = (geo.get("results") or [None])[0]
    if not hit:
        return None
    lat, lon = hit["latitude"], hit["longitude"]
    w = _get_json(
        "https://api.open-meteo.com/v1/forecast?latitude=%s&longitude=%s"
        "&current=temperature_2m,apparent_temperature,weather_code,"
        "wind_speed_10m,relative_humidity_2m,is_day"
        "&hourly=temperature_2m,precipitation_probability,weather_code"
        "&daily=temperature_2m_max,temperature_2m_min,sunrise,sunset,"
        "precipitation_probability_max"
        "&timezone=auto&forecast_days=2" % (lat, lon))
    cur = w.get("current") or {}
    code = cur.get("weather_code", 0)
    aqi = None
    try:
        q = _get_json(
            "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=%s"
            "&longitude=%s&current=european_aqi" % (lat, lon))
        aqi = (q.get("current") or {}).get("european_aqi")
    except Exception:
        pass  # 空气质量可选，失败不拖累天气
    return {
        "city": hit.get("name") or city,
        "temp": cur.get("temperature_2m"),
        "feels": cur.get("apparent_temperature"),
        "code": code,
        "text": _WMO.get(code, "未知"),
        "wind": cur.get("wind_speed_10m"),
        "aqi": aqi,
        "humidity": cur.get("relative_humidity_2m"),
        "is_day": cur.get("is_day", 1),
        "hourly": _parse_hourly(w, cur.get("time")),
        "today": _parse_daily(w),
        "updated": _hhmm(cur.get("time")),
        "stale": False,
    }


def fetch(city=None):
    """返回天气字典；彻底失败且无历史数据时返回 None。"""
    city = city or config.WEATHER_CITY
    now = time.monotonic()
    c = _CACHE.get(city)
    # 成功数据缓存 10 分钟；失败只压 60 秒，偶发网络抖动很快就能自愈
    ttl = (getattr(config, "WEATHER_CACHE_S", 600) if c and c["data"] is not None
           else getattr(config, "WEATHER_FAIL_CACHE_S", 60))
    if c and now - c["ts"] < ttl:
        if c["data"] is not None:
            return c["data"]
        if c["last"] is not None:
            return dict(c["last"], stale=True)
        return None  # 负缓存：接口刚失败过，别在每次刷新时反复外呼
    try:
        data = _load(city)
    except Exception as e:
        log.warning("天气获取失败: %s", e)
        data = None
    last = (c or {}).get("last")
    if data:
        _CACHE[city] = {"ts": now, "data": data, "last": data}
        return data
    _CACHE[city] = {"ts": now, "data": None, "last": last}
    return dict(last, stale=True) if last else None
