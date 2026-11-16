"""扫码登录回归：状态机 + token 构造（网络全部打桩，不真连小米）。"""
import asyncio
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="mijia-qr-")
os.environ["MIHOME_DATA_DIR"] = tmp

import config  # noqa: E402
import services.cloud as cloud  # noqa: E402
import services.qrauth as qrauth  # noqa: E402
from services.state import S  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


class FakeSession:
    """伪 aiohttp session：记录请求，返回预设响应。"""
    def __init__(self):
        self.calls = []
        self.closed = False

    async def close(self):
        self.closed = True

    def get(self, url, **kw):
        self.calls.append(url)
        return FakeResp(url)


class FakeResp:
    def __init__(self, url):
        self.url = url
        self.status = 200
        self.cookies = {}

    async def read(self):
        if "loginUrl" in self.url:
            return (b"&&&START&&&{\"qr\": \"https://x/qr\", \"lp\": \"https://x/lp\","
                    b"\"timeout\": 2}")
        if self.url.endswith("/qr"):
            return b"\x89PNG" + b"x" * 300
        if "/lp" in self.url:
            return b""  # 未扫码：空响应，轮询循环继续等到超时
        raise RuntimeError("unexpected " + self.url)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


# ---- 1. start()：拿到二维码 + waiting 状态 ----
def fake_call_ok(coro, timeout=None, what=""):
    fut = asyncio.new_event_loop().run_until_complete(_drain(coro))
    return fut


async def _drain(coro):
    return await coro


fake_session = FakeSession()
real_start = qrauth._do_start


async def fake_do_start():
    """绕过真实网络：直接构造 start 结果。"""
    info = {"session": fake_session, "account": None, "lp": "https://x/lp",
            "png": b"\x89PNG" + b"x" * 300, "expires": time.time() + 2}
    return info


qrauth._do_start = fake_do_start
ok(qrauth.start() is True, "start() 返回 True")
ok(qrauth.status() == "waiting", "start 后状态 waiting")
ok(len(qrauth.png()) > 100, "二维码 PNG 可取")
ok(qrauth.stop() is None, "stop() 可作废")

# 等 poller 线程自然超时（expires 2 秒 + 轮询循环退出）
deadline = time.time() + 10
while qrauth.status() == "waiting" and time.time() < deadline:
    time.sleep(0.3)
ok(qrauth.status() == "expired", "超时后状态 expired（不误报 error）")

# ---- 2. _finish_login：token 构造 + 落盘 ----
class FakeAccount:
    token = None


class FakeMorsel:
    def __init__(self, v):
        self.value = v


class LocResp:
    status = 200
    cookies = {"serviceToken": FakeMorsel("ST_abc123")}

    async def read(self):
        return b"{}"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


loc_session = FakeSession()
loc_session.get = lambda url, **kw: LocResp()
qrauth._QR["session"] = loc_session
qrauth._QR["account"] = FakeAccount()

import json  # noqa: E402

data = {"location": "https://x/sts?x=1", "userId": 12345,
        "passToken": "PT_x", "ssecurity": "SEC_x"}
loop = asyncio.new_event_loop()


class FakeMiIO:
    def __init__(self, account):
        pass

    async def device_list(self, mode=None):
        return [{"did": "1", "isOnline": True}]


import miservice  # noqa: E402
miservice.MiIOService = FakeMiIO
loop.run_until_complete(qrauth._finish_login(loc_session, data))

ok(S["logged_in"] is True, "扫码成功后置登录态")
ok(S["user"] == "扫码用户 12345", "登录用户名记录")
with open(config.TOKEN_PATH, "r") as f:
    token = json.load(f)
ok(token["userId"] == 12345 and token["passToken"] == "PT_x",
   "token 落盘含 userId/passToken")
ok(token["xiaomiio"] == ["SEC_x", "ST_abc123"], "xiaomiio = [ssecurity, serviceToken]")
ok(qrauth.status() == "ok", "状态 ok")
mode = oct(os.stat(config.TOKEN_PATH).st_mode)[-3:]
ok(mode == "600", "token 文件权限 600")

# ---- 3. -127 限流感知 ----
ok(cloud.rate_limit_wait(
    'Error x: {"code":-127,"message":"client withdraw",'
    '"result":{"wait_second":30}}') == 32,
   "rate_limit_wait 解析 wait_second=30 → 32")
ok(cloud.rate_limit_wait('Error x: {"code":-127,"message":"client withdraw"}') == 15,
   "rate_limit_wait 无 wait_second → 默认 15")
ok(cloud.rate_limit_wait("Error x: {\"code\":-709}") == 0,
   "非限流错误 → 0")

# ---- 4. _device_list_with_retry：首次 -127，重试成功 ----
class FlakyMiIO:
    def __init__(self):
        self.n = 0

    async def device_list(self, mode=None):
        self.n += 1
        if self.n == 1:
            raise RuntimeError(
                'Error https://api.io.mi.com/app/home/device_list: '
                '{"code":-127,"message":"client withdraw",'
                '"result":{"wait_second":0}}')
        return [{"did": "1", "isOnline": True}]


flaky = FlakyMiIO()
got = loop.run_until_complete(qrauth._device_list_with_retry(flaky))
ok(got and flaky.n == 2, "限流后按 wait_second 重试成功（第 2 次拿到设备）")

# ---- 5. 持续限流不判登录失败：token 有效，设备空、后台补拉 ----
class AlwaysLimitedMiIO(FlakyMiIO):
    def __init__(self, account):
        super().__init__()
    async def device_list(self, mode=None):
        self.n += 1
        raise RuntimeError(
            'Error https://api.io.mi.com/app/home/device_list: '
            '{"code":-127,"message":"client withdraw",'
            '"result":{"wait_second":0}}')


S["logged_in"] = False
S["devices"] = []
qrauth._QR["session"] = loc_session
qrauth._QR["account"] = FakeAccount()
miservice.MiIOService = AlwaysLimitedMiIO
loop.run_until_complete(qrauth._finish_login(loc_session, data))
ok(S["logged_in"] is True, "持续限流时仍完成登录（token 有效）")
ok(S["devices"] == [], "限流时设备列表先为空，由后台补拉")
ok(qrauth.status() == "ok", "限流场景状态仍 ok（不报 error）")

# ---- 6. 风控冷却门 ----
cloud._note_rate_limited(
    '{"code":-127,"message":"client withdraw","result":{"wait_second":0}}')
ok(cloud.cooling() > 0, "-127 触发全局冷却门")
import services.live as livemod  # noqa: E402
ok(livemod.batch_read([("d1", 2, 1)]) == {}, "冷却期内批量读跳过（沿用缓存值）")
with cloud._cooldown_lock:
    cloud._cooldown_until = 0.0
ok(cloud.cooling() == 0, "冷却复位")

print("qrauth_test: %d 项通过" % ok_n[0])
