"""修正 miservice 云端请求头里写死的"别人账号身份"。

miservice 自带的 UA_MIIO 是库作者的样例串：

    iOS-14.4-6.0.103-iPhone12,3--D774...BE9-8816080-84A3...-iPhone
                                  ^DeviceId      ^UserId

小米云端会核对 UA 里的 UserId / DeviceId 与 cookie、token 里的身份。
不一致时返回 HTTP 429 + {"code":-127,"message":"client withdraw",
"result":{"wait_second":30,...}} —— 长得完全像限流，实际上是拒绝非法
客户端，**等多久都不会自己恢复**。

这里在每次云端请求发出前，按当前 token 的真实身份重写 UA。只替换 UA，
其余签名、cookie、请求逻辑全部沿用库原实现，库升级时不会失配。
"""
import re

_installed = False
_ORIG_UA = None


def _ua_for(token):
    """按 token 里的 deviceId/userId 生成合法的云端 UA。"""
    from miservice import miioservice as ms

    ua = _ORIG_UA or ms.UA_MIIO
    did = str(token.get("deviceId") or "")
    uid = str(token.get("userId") or "")
    if not did or not uid:
        return ua
    # UA 中 "--<DeviceId>-<UserId>-" 这一段换成当前账号
    fixed, n = re.subn(r"--[0-9A-Za-z]+-(\d+)-",
                       lambda m: "--%s-%s-" % (did, uid), ua, count=1)
    if n:
        return fixed
    # 库 UA 格式若变了，退化到一个已验证可用的新版格式
    return ("iOS-26.3.1-11.3.203-iPhone17,2--%s-%s-"
            "84A3F44E137B71AE-iPhone" % (did, uid))


def install():
    """幂等安装；所有 MiIOService 实例自动生效。"""
    global _installed, _ORIG_UA
    if _installed:
        return
    try:
        from miservice import miioservice as ms
    except ImportError as e:
        import logx
        logx.get("mihome.mi_patch").warning("miservice 不可用，跳过 UA 修正: %s", e)
        return

    _ORIG_UA = ms.UA_MIIO
    orig = ms.MiIOService.miio_request

    async def miio_request(self, uri, data):
        token = getattr(self.account, "token", None)
        if not token and getattr(self.account, "token_store", None):
            token = await self.account.token_store.load_token()
        if token:
            ms.UA_MIIO = _ua_for(token)
        return await orig(self, uri, data)

    ms.MiIOService.miio_request = miio_request
    _installed = True
