"""批量读写参数格式回归（全程打桩，不连小米云端）。

miservice.miot_request 内部会包一层 {'params': ...}，调用方必须直接传数组；
返回值已经是 result 数组，不能再取一次 ["result"]。
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import services.cloud as cloud  # noqa: E402
import services.live as live  # noqa: E402
from services.state import S  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)
    ok_n[0] += 1


class FakeService:
    def __init__(self):
        self.calls = []

    async def miot_request(self, cmd, params):
        self.calls.append((cmd, params))
        return [{"did": "d1", "siid": 2, "piid": 1,
                 "value": True, "code": 0}]

    async def miot_set_props(self, did, props):
        self.calls.append(("set_props", did, props))
        return [0]


class PlainService:
    """完全没有 miot_set_props 属性，用于验证 fallback 分支。"""
    def __init__(self):
        self.calls = []

    async def miot_request(self, cmd, params):
        self.calls.append((cmd, params))
        return []


orig_call = cloud.call
cloud.call = lambda coro, timeout=None, what="": asyncio.run(coro)
try:
    svc = FakeService()
    S["service"] = svc
    out = live.batch_read([("d1", 2, 1)])
    ok(svc.calls[0][0] == "prop/get", "走 prop/get")
    ok(svc.calls[0][1] == [{"did": "d1", "siid": 2, "piid": 1}],
       "参数直接是数组，未多包 params")
    ok(out == {("d1", 2, 1): True}, "返回值按 (did,siid,piid) 正确解析")

    svc2 = FakeService()
    S["service"] = svc2
    plan = [("d%d" % i, 2, 1) for i in range(65)]
    live.batch_read(plan)
    ok(len(svc2.calls) == 3, "65 条参数分 3 批")
    ok([len(c[1]) for c in svc2.calls] == [30, 30, 5], "分批大小 30/30/5")

    svc3 = FakeService()
    S["service"] = svc3
    live.set_prop("d1", 2, 1, False)
    ok(svc3.calls[0][0] == "set_props", "优先用库自带写入方法")
    ok(svc3.calls[0][1] == "d1", "did 作为独立参数传入")
    ok(svc3.calls[0][2] == [(2, 1, False)], "props 为 (siid,piid,value) 元组列表")

    svc4 = PlainService()
    S["service"] = svc4
    live.set_prop("d1", 2, 1, False)
    ok(svc4.calls[0][0] == "prop/set", "fallback 走 prop/set")
    ok(isinstance(svc4.calls[0][1], list), "fallback 参数也是数组")
finally:
    cloud.call = orig_call
    S["service"] = None

print("batch_read_test: %d 项通过" % ok_n[0])
