"""miservice 云端 UA 身份修正回归（全程打桩，不连小米云端）。"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from miservice import MiIOService  # noqa: E402
from services import mi_patch  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if not cond:
        raise AssertionError(msg)
    ok_n[0] += 1


TOKEN = {
    "deviceId": "ABCDEF0123456789",
    "userId": 1000001,
    "passToken": "x",
    "xiaomiio": ["QUFBQUFBQUFBQUFBQUFBQQ==", "service-token"],
}

mi_patch.install()
mi_patch.install()  # 幂等
ok(mi_patch._installed, "install 幂等生效")

ua = mi_patch._ua_for(TOKEN)
ok("1000001" in ua, "UA 带当前账号 userId")
ok("ABCDEF0123456789" in ua, "UA 带真实 deviceId")
ok("8816080" not in ua, "UA 不含库作者的 userId")
ok("D7744744F7AF32F0544445285880DD63E47D9BE9" not in ua, "UA 不含库作者的 deviceId")
ok(ua.startswith("iOS-"), "UA 保留库原有格式")


class FakeAccount:
    def __init__(self, token):
        self.token = token
        self.token_store = None
        self.captured = {}

    async def mi_request(self, sid, url, data, headers):
        self.captured["headers"] = headers
        cookies = {}
        if callable(data):
            data(self.token, cookies)  # 触发签名，确保未破坏库原逻辑
        self.captured["cookies"] = cookies
        return {"result": {"list": [{"did": "d1"}]}}


async def main():
    acc = FakeAccount(TOKEN)
    got = await MiIOService(acc).device_list("full")
    ok(got == [{"did": "d1"}], "device_list 结果透传")
    h = acc.captured["headers"]
    ok("1000001" in h["User-Agent"], "实际请求 UA 带当前账号 userId")
    ok("8816080" not in h["User-Agent"], "实际请求 UA 不含他人 userId")
    ok(h.get("x-xiaomi-protocal-flag-cli") == "PROTOCAL-HTTP2", "保留 HTTP2 协议头")
    ok(acc.captured["cookies"].get("PassportDeviceId") == TOKEN["deviceId"],
       "PassportDeviceId 与 token 一致")


asyncio.run(main())
print("mi_patch_test: %d 项通过" % ok_n[0])
