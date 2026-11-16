"""卡片布局持久化：尺寸覆盖 + 拖拽顺序。

layout.json 结构：
    {"sizes": {"<did>": "sm|md|lg"}, "order": ["<did>", ...]}
sizes 是逐设备的尺寸覆盖（不写则用自动尺寸）；order 是设备展示顺序，
仅包含用户拖拽过的 did，未出现的设备按默认顺序排在末尾。
"""
import json
import os
import tempfile

import config

_VALID = ("sm", "md", "lg")


def load():
    try:
        with open(config.LAYOUT_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {"sizes": {}, "order": []}
    if not isinstance(data, dict):
        return {"sizes": {}, "order": []}
    sizes = data.get("sizes") or {}
    order = data.get("order") or []
    if not isinstance(sizes, dict):
        sizes = {}
    if not isinstance(order, list):
        order = []
    return {"sizes": sizes, "order": [str(x) for x in order]}


def save(data):
    """原子写：先写临时文件再 rename，避免半截文件损坏。"""
    os.makedirs(os.path.dirname(config.LAYOUT_PATH), exist_ok=True)
    tmp = config.LAYOUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.LAYOUT_PATH)


def set_size(did, size):
    if size not in _VALID:
        raise ValueError("invalid size: %r" % size)
    data = load()
    data["sizes"][str(did)] = size
    save(data)
    return data


def set_order(order):
    data = load()
    data["order"] = [str(x) for x in order]
    save(data)
    return data
