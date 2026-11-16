"""扫码登录：小米账号 QR 长轮询（与米家 App 扫码登录同一套协议）。

流程（接口事实来自小米账号公开协议，多项目交叉验证）：
  1. GET account.xiaomi.com/longPolling/loginUrl?sid=xiaomiio&...
     → {qr: 二维码图片地址, lp: 长轮询地址, timeout: 有效期秒数}
  2. GET qr → PNG（小米直接渲染好，无需本地 QR 库）
  3. 后台长轮询 GET lp（阻塞至扫码确认；超时 ~35s/次，循环至有效期）
     → {userId, passToken, ssecurity, location, ...}
  4. GET location（同 session 带 cookie）→ 响应 Set-Cookie: serviceToken
  5. 组装 miservice 格式 token：
     {deviceId, userId, passToken, xiaomiio: [ssecurity, serviceToken]}
     原子写 TOKEN_PATH，并构造 MiAccount/MiIOService 置为登录态。

状态机：idle → waiting → ok | expired | error（stop 可中途作废）
"""
import asyncio
import json
import os
import threading
import time

import aiohttp

import config
import logx
import services.cloud as cloud
from services.state import S, _LOGIN_LOCK

log = logx.get("mihome.qr")

try:
    from miservice.miaccount import UA_LOGIN, get_random, parse_resp
except ImportError:  # 兼容旧版 miservice
    UA_LOGIN = ("APP/com.xiaomi.mihome APPV/6.0.103 iosPassportSDK/3.9 "
                "iOS/16.3.1 L/zh_CN")
    get_random = None
    parse_resp = None

_LOGIN_URL = "https://account.xiaomi.com/longPolling/loginUrl"

_QR = {
    "lock": threading.RLock(),
    "session": None,     # aiohttp.ClientSession（QR 与后续 MiIOService 共用）
    "account": None,     # MiAccount
    "lp": "",
    "png": b"",
    "expires": 0.0,
    "status": "idle",    # idle | waiting | ok | expired | error
    "err": "",
    "poller": None,
    "stop": False,
}


def status() -> str:
    with _QR["lock"]:
        return _QR["status"]


def error() -> str:
    with _QR["lock"]:
        return _QR["err"]


def png() -> bytes:
    with _QR["lock"]:
        return _QR["png"] or b""


def stop():
    """作废当前二维码（切页签/重新开始时调用）。"""
    with _QR["lock"]:
        _QR["stop"] = True


def _reset(status_, err=""):
    with _QR["lock"]:
        _QR["stop"] = False
        _QR["status"] = status_
        _QR["err"] = err


def _close_session(session):
    """在事件循环里安全关闭 session（不能跨线程直接 close）。"""
    if session is None or session.closed:
        return
    try:
        cloud.call(session.close(), timeout=10, what="qr_close")
    except Exception as e:
        log.warning("关闭旧 QR session 失败: %s", e)


def start():
    """发起一次扫码登录。返回 True 表示二维码已就绪。"""
    if S.get("logged_in"):
        return False
    with _QR["lock"]:
        old_session = _QR["session"] if _QR["status"] != "ok" else None
        _QR["stop"] = True  # 通知旧轮询线程退出
    _close_session(old_session)
    _reset("waiting")
    try:
        info = cloud.call(_do_start(), timeout=30, what="qr_start")
    except Exception as e:
        log.warning("获取二维码失败: %s", e)
        _reset("error", str(e)[:160])
        return False
    with _QR["lock"]:
        _QR.update(info)
        _QR["stop"] = False
        _QR["status"] = "waiting"
    t = threading.Thread(target=_poll_loop, name="qr-poll", daemon=True)
    with _QR["lock"]:
        _QR["poller"] = t
    t.start()
    return True


async def _do_start():
    from urllib.parse import quote
    session = aiohttp.ClientSession()
    ms = int(time.time() * 1000)
    url = (_LOGIN_URL
           + "?_qrsize=260"
           + "&qs=" + quote("?sid=xiaomiio&_json=true", safe="")
           + "&callback=" + quote("https://sts.api.io.mi.com/sts", safe="")
           + "&_hasLogo=true&sid=xiaomiio&serviceParam="
           + "&_locale=zh_CN&_dc=" + str(ms))
    headers = {"User-Agent": UA_LOGIN}
    async with session.get(url, headers=headers) as r:
        data = _parse(await r.read())
    if not data.get("lp") or not data.get("qr"):
        raise RuntimeError("loginUrl 响应异常: %s" % str(data)[:160])
    async with session.get(data["qr"], headers=headers) as r:
        image = await r.read()
    if not image[:4] == b"\x89PNG" or len(image) < 100:
        raise RuntimeError("二维码图片异常（%d 字节）" % len(image))
    timeout_s = min(int(data.get("timeout") or 300), 600)
    from miservice import MiAccount
    account = MiAccount(session, "", "", token_store=config.TOKEN_PATH)
    return {"session": session, "account": account, "lp": str(data["lp"]),
            "png": image, "expires": time.time() + timeout_s}


def _parse(raw: bytes) -> dict:
    if parse_resp:
        return parse_resp(raw)
    import json as _json
    prefix = b"&&&START&&&"
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    return _json.loads(raw) if raw else {}


def _poll_loop():
    deadline = _QR["expires"] + 5
    try:
        cloud.call(_do_poll(deadline),
                   # +195s：登录成功后的 device_list 可能被 -127 限流，
                   # 重试（最多 3 次 × wait_second）需要额外时间窗
                   timeout=max(30.0, deadline - time.time() + 195),
                   what="qr_poll")
    except Exception as e:
        log.info("扫码轮询结束: %s", e)
        with _QR["lock"]:
            if _QR["status"] == "waiting":
                if "过期" in str(e) or "Timeout" in str(type(e).__name__):
                    _QR["status"] = "expired"
                else:
                    _QR["status"] = "error"
                    _QR["err"] = str(e)[:160]
    finally:
        # 未登录成功的 session 收掉；登录成功的留给 MiIOService 用
        with _QR["lock"]:
            keep = _QR["status"] == "ok"
            session = _QR["session"]
        if not keep:
            _close_session(session)
            with _QR["lock"]:
                if _QR["status"] == "waiting":
                    _QR["status"] = "expired"


async def _do_poll(deadline: float):
    session = _QR["session"]
    headers = {"User-Agent": UA_LOGIN}
    while time.time() < deadline and not _QR["stop"]:
        try:
            async with session.get(_QR["lp"], headers=headers,
                                    timeout=aiohttp.ClientTimeout(total=40)) as r:
                if r.status != 200:
                    await asyncio.sleep(1)
                    continue
                data = _parse(await r.read())
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError):
            await asyncio.sleep(1)  # 服务端 ~30s 放一次行，属正常，接着轮
            continue
        if data.get("location") and data.get("userId"):
            await _finish_login(session, data)
            return
        # 未含 location 的中间响应（未确认等）→ 继续等
        await asyncio.sleep(1)
    raise TimeoutError("二维码已过期")


async def _finish_login(session, data: dict):
    """扫码确认完成：换 serviceToken、落盘 token、置登录态。"""
    # serviceToken 在 location 响应的 Set-Cookie 里
    service_token = None
    async with session.get(data["location"], headers={"User-Agent": UA_LOGIN}) as r:
        await r.read()
        morsel = r.cookies.get("serviceToken")
        if morsel:
            service_token = morsel.value
    if not service_token and data.get("nonce"):
        # 兜底：走 miservice 的 clientSign 签名通道
        account = _QR["account"]
        service_token = await account._securityTokenService(
            data["location"], data["nonce"], data["ssecurity"])
    if not service_token:
        raise RuntimeError("未取得 serviceToken：%s" % str(data)[:160])

    device_id = config.device_id()  # 稳定设备指纹（持久化，防风控）
    token = {
        "deviceId": device_id,
        "userId": data["userId"],
        "passToken": data.get("passToken") or "",
        "xiaomiio": [data["ssecurity"], service_token],
    }
    # 原子落盘（先写临时文件再替换 + 收紧权限，防半截 token）
    tmp = config.TOKEN_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(token, f, indent=2)
    os.chmod(tmp, 0o600)
    os.replace(tmp, config.TOKEN_PATH)

    account = _QR["account"]
    account.token = token
    from miservice import MiIOService
    service = MiIOService(account)
    # 实测验证：拉一次设备列表。刚换发的 token 立刻拉列表会被小米风控
    # 限流（code:-127 client withdraw，要求等 wait_second 秒）——带退避重试；
    # 重试耗尽也不算登录失败（token 本身已落盘有效），先进主界面，
    # 由后台线程继续补拉设备列表。
    devices = []
    try:
        devices = await _device_list_with_retry(service)
    except Exception as e:
        wait = cloud.rate_limit_wait(e)
        if wait:
            log.warning("设备列表持续被限流，先完成登录，后台补拉: %s", str(e)[:120])
            threading.Thread(target=_backfill_devices, name="qr-backfill",
                             daemon=True).start()
        else:
            raise  # 非限流错误（token 真不可用）才算登录失败
    from services import devices as _dev
    # 扫码登录是 async 路径，不能用同步 cloud.call（会自己等自己死锁），
    # 直接 await 云端家庭列表，再复用纯函数补 home/room。
    try:
        homes = await asyncio.wait_for(service.home_list(), timeout=20)
    except Exception as e:
        homes = []
        log.warning("扫码登录后拉家庭列表失败: %s", str(e)[:120])
    _dev.apply_room_loc(devices or [], _dev._rooms_from_homes(homes))
    with _LOGIN_LOCK:
        S["account"], S["service"] = account, service
        S["devices"] = devices or []
        S["logged_in"] = True
        S["user"] = "扫码用户 %s" % data["userId"]
        S["last_refresh"] = time.time()
        if devices:
            _dev._remember_devices(devices)
    with _QR["lock"]:
        _QR["status"] = "ok"
    log.info("扫码登录成功 userId=%s 设备 %d 台", data["userId"], len(devices or []))


async def _device_list_with_retry(service, tries=3):
    """拉设备列表；被 -127 限流时递增退避（wait、wait×2…），防续期封禁。"""
    for i in range(tries):
        try:
            return await service.device_list("full")
        except Exception as e:
            wait = cloud.rate_limit_wait(e)
            if not wait or i == tries - 1:
                raise
            backoff = min(wait * (i + 1), 90)
            log.info("设备列表被限流，%d 秒后重试（第 %d/%d 次）",
                     backoff, i + 1, tries)
            await asyncio.sleep(backoff)


def _backfill_devices():
    """登录后设备列表被限流拉不到时，后台按递增间隔补拉直至拿到。"""
    from services import devices as _dev
    for gap in (30, 60, 90, 120, 180, 180):
        time.sleep(gap)
        if not S.get("logged_in") or not S.get("service"):
            return
        got = _dev.refresh_devices()
        if got:
            log.info("后台补拉设备列表成功：%d 台", len(got))
            return
