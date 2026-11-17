#!/usr/bin/env python3
"""启动入口：python3 run.py 后浏览器打开 http://127.0.0.1:8765"""
import os
import sys
import threading

import config


def _setup_ca_certs():
    """让 ssl/aiohttp 使用随包携带的 CA 证书，避免登录扫码时 SSL 校验失败。

    Windows 的 Python 嵌入版不自带证书链，默认去找 C:\\Program Files\\Common Files\\SSL\\cert.pem
    （通常不存在），导致访问 account.xiaomi.com 报 CERTIFICATE_VERIFY_FAILED。
    certifi 随依赖一起打包，这里把它的证书路径告诉 ssl。
    """
    try:
        import certifi
        os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    except Exception:
        pass


def _open_browser(url):
    """尽力打开浏览器，并把结果写到窗口日志，便于排障。失败不阻断服务。"""
    try:
        if sys.platform == "win32":
            os.startfile(url)  # Windows 原生，等价于双击网址
        else:
            import webbrowser
            webbrowser.open(url)
        print("[启动] 已请求打开浏览器：%s" % url, flush=True)
    except Exception as exc:
        print("[启动] 自动打开浏览器失败：%r" % (exc,), flush=True)
        print("[启动] 请手动打开浏览器访问：%s" % url, flush=True)


def main():
    config.ensure_dirs()
    _setup_ca_certs()
    if not config.NO_BROWSER:
        url = "http://%s:%s" % (config.HOST, config.PORT)
        threading.Timer(1.5, _open_browser, args=(url,)).start()
    from app import main as serve
    serve()


if __name__ == "__main__":
    main()
