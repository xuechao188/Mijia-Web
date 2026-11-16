"""设备缓存：冷启动秒开 + 上次在线时间（补齐未实现项 #3）。

三条硬原则：
  1. 缓存只加速、不添堵 —— 读不到/读坏/版本对不上，一律当没有缓存
  2. 结构变了就作废 —— CACHE_VERSION 一改旧缓存自动失效
  3. 写失败不阻塞 —— 写不进去下次刷新再写
"""
import json
import os
import time

import config

_lock = __import__("threading").RLock()


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
    """返回 {"version":.., "devices":[...], "last_seen":{did:ts}}，坏缓存返回 None。"""
    try:
        with open(config.DEV_CACHE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if data.get("version") != config.CACHE_VERSION:
        return None
    devs = data.get("devices")
    if not isinstance(devs, list):
        return None
    for d in devs:
        if not isinstance(d, dict) or "did" not in d:
            return None  # 元素级校验：缺 did 整份作废
    return data


def save(devices, last_seen=None):
    """落盘设备视图。任何未确认能力的猜测（on_guess）都会让整份不写。"""
    for d in devices or []:
        if d.get("on_guess"):
            return False  # 半成品不覆盖好快照
    payload = {
        "version": config.CACHE_VERSION,
        "devices": devices or [],
        "last_seen": last_seen or {},
    }
    with _lock:
        return _atomic_write(config.DEV_CACHE_PATH, payload)


def touch_seen(did, ts=None):
    """更新单设备最近在线时间（内存态，随下次 save 落盘）。"""
    with _lock:
        _seen.setdefault("m", {})[str(did)] = ts or time.time()


_seen = {}


def seen_map():
    with _lock:
        return dict(_seen.get("m", {}))


def merge_seen_from_cache(cache):
    """把磁盘缓存的 last_seen 并进内存。只补缺失的键，绝不覆盖内存里更新的值。"""
    if cache and isinstance(cache.get("last_seen"), dict):
        with _lock:
            m = _seen.setdefault("m", {})
            for k, v in cache["last_seen"].items():
                m.setdefault(str(k), v)
