#!/usr/bin/env python3
"""启动入口：python3 run.py 后浏览器打开 http://127.0.0.1:8765"""
import webbrowser
import threading

import config


def main():
    config.ensure_dirs()
    if not config.NO_BROWSER:
        threading.Timer(1.5, lambda: webbrowser.open(
            "http://%s:%s" % (config.HOST, config.PORT))).start()
    from app import main as serve
    serve()


if __name__ == "__main__":
    main()
