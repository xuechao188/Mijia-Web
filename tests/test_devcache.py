"""设备缓存回归：秒开、last_seen（未实现项 #3）、原子写、测试隔离、on_guess 不落盘。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
tmp = tempfile.mkdtemp(prefix="mijia-cache-")
os.environ["MIHOME_DATA_DIR"] = tmp

import config  # noqa: E402
from services import devcache  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


ok(config.DATA_DIR.startswith(tmp), "数据目录被环境变量隔离到临时目录")

# 正常保存/读取 + last_seen
devs = [{"did": "100", "name": "灯", "on_siid": 2, "on_piid": 1,
         "cap": {"on": True}, "controls": [], "on_guess": False}]
seen = {"100": 1700000000.0}
ok(devcache.save(devs, seen) is True, "好快照可保存")
cache = devcache.load()
ok(cache and cache["devices"][0]["did"] == "100", "缓存可读回")
ok(cache["last_seen"]["100"] == 1700000000.0, "last_seen 落盘（未实现项 #3）")

# on_guess 半成品不落盘：文件字节不变
before = open(config.DEV_CACHE_PATH, "rb").read()
bad = [{"did": "200", "name": "猜", "on_guess": True}]
ok(devcache.save(bad) is False, "on_guess 存在时拒绝落盘")
after = open(config.DEV_CACHE_PATH, "rb").read()
ok(before == after, "半成品不会覆盖好快照")

# 缺 did 的坏缓存整份作废
with open(config.DEV_CACHE_PATH, "w", encoding="utf-8") as f:
    f.write('{"version": %d, "devices": [{"name": "无did"}]}' % config.CACHE_VERSION)
ok(devcache.load() is None, "缺 did 的缓存整份作废")

# 版本不符作废
with open(config.DEV_CACHE_PATH, "w", encoding="utf-8") as f:
    f.write('{"version": 1, "devices": [{"did": "1"}]}')
ok(devcache.load() is None, "CACHE_VERSION 不符自动作废")

# touch_seen 合并
devcache.touch_seen("300", 123.0)
ok(devcache.seen_map().get("300") == 123.0, "touch_seen 记录在线时间")

# 合并只补缺不覆盖（修 bug：原来 update 会拿磁盘旧值盖掉内存新值）
devcache.touch_seen("100", 9999.0)   # 内存里刷新为最新
devcache.merge_seen_from_cache(
    {"last_seen": {"100": 1.0, "400": 55.0}})  # 磁盘旧值不得覆盖 9999
m = devcache.seen_map()
ok(m.get("100") == 9999.0, "合并不覆盖内存里更新的 last_seen")
ok(m.get("400") == 55.0, "合并补上内存缺失的键")

print("devcache_test: %d 项通过" % ok_n[0])
