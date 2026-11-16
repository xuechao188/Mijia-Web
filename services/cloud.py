"""云端调用执行器。

一个后台 asyncio 事件循环 + run_coroutine_threadsafe：
  - call(coro, timeout)：超时**真正取消**协程（不只放弃等待），防僵尸协程堆积
  - 控制类用短超时、采集类用长超时，互不拖累
"""
import asyncio
import re
import threading
import time

import config
import logx
from services import mi_patch

# 云端请求必须用当前账号的真实身份，否则小米回 -127 client withdraw
mi_patch.install()

log = logx.get("mihome.cloud")

_loop = None
_thread = None
_ready = threading.Event()


def _run_loop():
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)
    _ready.set()
    _loop.run_forever()


def start():
    global _thread
    mi_patch.install()  # 幂等兜底
    if _thread and _thread.is_alive():
        return
    _ready.clear()
    _thread = threading.Thread(target=_run_loop, name="cloud-loop", daemon=True)
    _thread.start()
    _ready.wait(10)


def call(coro, timeout=None, what=""):
    """在云端循环里执行协程，超时真取消。返回协程结果。"""
    start()
    timeout = timeout or config.CLOUD_TIMEOUT_S
    fut = asyncio.run_coroutine_threadsafe(coro, _loop)
    t0 = time.time()
    try:
        return fut.result(timeout)
    except Exception as e:
        fut.cancel()  # 真正取消，不留僵尸协程
        _note_rate_limited(e)
        log.warning("call 失败 what=%s elapsed=%.1fs", what, time.time() - t0)
        raise


# ------------------------------------------------------------ 风控冷却门
# 小米云端对高频请求回 -127 client withdraw（要求 wait_second 秒退避）。
# 任何调用撞上 -127 都会全局冷却：冷却期内批量读/列表刷新直接跳过
# （用缓存值），防止 3 秒轮询持续撞墙、不断续期封禁窗口。
_cooldown_until = 0.0
_cooldown_lock = threading.Lock()


def cooling() -> float:
    """剩余冷却秒数；>0 表示风控退避中，云端读应跳过。"""
    with _cooldown_lock:
        return max(0.0, _cooldown_until - time.time())


def _note_rate_limited(err):
    global _cooldown_until
    wait = rate_limit_wait(err)
    if not wait:
        return
    with _cooldown_lock:
        _cooldown_until = max(_cooldown_until, time.time() + wait)
    log.info("小米风控退避（-127），全局冷却 %d 秒", wait)


def rate_limit_wait(err) -> int:
    """异常若是小米风控限流（code:-127 client withdraw），返回建议等待秒数；否则 0。

    刚换发 token（扫码/登录成功）后立刻拉设备列表常被限流，
    服务端会带 wait_second 提示等待时长。
    """
    msg = str(err)
    if "-127" not in msg and "client withdraw" not in msg:
        return 0
    m = re.search(r'"wait_second"\s*:\s*(\d+)', msg)
    if m:
        return min(int(m.group(1)) + 2, 60)
    return 15
