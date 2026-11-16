#!/usr/bin/env python3
"""Mijia-Web 命令行入口：让脚本 / AI agent 直接控制米家设备。

前提：本机服务已启动（python3 run.py）。本工具只调用本地 HTTP API，
不重复实现业务逻辑；所有输出人类可读，加 --json 时输出 JSON（给程序用）。

用法示例：
  python3 cli.py devices                # 列出设备
  python3 cli.py on 123456789           # 开设备
  python3 cli.py off 123456789          # 关设备
  python3 cli.py toggle 123456789 on2   # 切多键开关第 2 路
  python3 cli.py set 123456789 2 3 50   # 写属性 siid=2 piid=3 value=50
  python3 cli.py scenes                 # 列出场景
  python3 cli.py scene 987654           # 执行场景
  python3 cli.py events                 # 最近事件
  python3 cli.py weather                # 天气
"""
import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"


def call(path, body=None):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json", "Origin": BASE}
    # 公网实例设置了访问密码时，CLI 从同名环境变量取凭据（本机使用不需要）
    user = os.environ.get("MIHOME_ACCESS_USER", "")
    pwd = os.environ.get("MIHOME_ACCESS_PASSWORD", "")
    if user and pwd:
        token = base64.b64encode(("%s:%s" % (user, pwd)).encode()).decode()
        headers["Authorization"] = "Basic " + token
    req = urllib.request.Request(
        url, data=data, method="POST" if data else "GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.URLError as e:
        print("无法连接本地服务 %s（先运行 python3 run.py）：%s" % (BASE, e), file=sys.stderr)
        sys.exit(2)
    except json.JSONDecodeError:
        print("服务返回了非 JSON 内容", file=sys.stderr)
        sys.exit(2)


def out(obj, as_json):
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2))
    return obj


def main():
    global BASE
    ap = argparse.ArgumentParser(description="Mijia-Web CLI")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    ap.add_argument("--base", default=BASE, help="服务地址，默认 %s" % BASE)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("devices")
    p = sub.add_parser("on"); p.add_argument("did"); p.add_argument("--key", default="on")
    p = sub.add_parser("off"); p.add_argument("did"); p.add_argument("--key", default="on")
    p = sub.add_parser("toggle"); p.add_argument("did")
    p.add_argument("key", nargs="?", default="on", help="多键开关路：on1/on2")
    p = sub.add_parser("set")
    p.add_argument("did"); p.add_argument("siid", type=int)
    p.add_argument("piid", type=int); p.add_argument("value")
    sub.add_parser("scenes")
    p = sub.add_parser("scene"); p.add_argument("scene_id")
    p.add_argument("--home", default="", help="home_id")
    sub.add_parser("events")
    sub.add_parser("weather")
    sub.add_parser("ping")

    args = ap.parse_args()
    BASE = args.base

    if args.cmd == "ping":
        r = call("/api/ping")
        out(r, args.json)
        if not args.json:
            print("服务正常 v%s" % r.get("version"))

    elif args.cmd == "devices":
        r = call("/api/devices")
        out(r, args.json)
        if not args.json:
            for d in r.get("devices", []):
                live = {}
                print("%-14s %-16s %-8s %s" % (
                    d.get("did"), (d.get("name") or "")[:16],
                    "在线" if d.get("online") else "离线",
                    d.get("product") or d.get("model") or ""))

    elif args.cmd in ("on", "off", "toggle"):
        if args.cmd == "toggle":
            r = call("/api/live?quick=1")
            cur = (r.get("live") or {}).get(args.did, {}).get(args.key)
            on = not bool(cur)
        else:
            on = args.cmd == "on"
        r = call("/api/switch", {"did": args.did, "on": on, "key": args.key})
        out(r, args.json)
        if not args.json:
            print("已%s %s（%s）" % ("开" if on else "关", args.did, args.key)
                  if r.get("ok") else ("失败：%s" % r.get("error")))

    elif args.cmd == "set":
        v = args.value
        try:
            v = json.loads(v)  # 数字/布尔/字符串都吃
        except ValueError:
            pass
        r = call("/api/set", {"did": args.did, "siid": args.siid,
                              "piid": args.piid, "value": v})
        out(r, args.json)
        if not args.json:
            print("已设置" if r.get("ok") else "失败：%s" % r.get("error"))

    elif args.cmd == "scenes":
        r = call("/api/scenes")
        out(r, args.json)
        if not args.json:
            for s in r.get("scenes", []):
                print("%-16s %s" % (s.get("scene_id"), s.get("name")))

    elif args.cmd == "scene":
        r = call("/api/scenes/run", {"scene_id": args.scene_id,
                                     "home_id": args.home})
        out(r, args.json)
        if not args.json:
            print("场景已执行" if r.get("ok") else "失败：%s" % r.get("error"))

    elif args.cmd == "events":
        r = call("/api/events")
        out(r, args.json)
        if not args.json:
            for e in r.get("events", []):
                print("%s  [%s] %s" % (e.get("time"), e.get("type"), e.get("text")))

    elif args.cmd == "weather":
        r = call("/api/weather")
        out(r, args.json)
        if not args.json and r.get("weather"):
            w = r["weather"]
            print("%s %s° %s 体感%s° AQI %s" % (
                w.get("city"), w.get("temp"), w.get("text"),
                w.get("feels"), w.get("aqi")))


if __name__ == "__main__":
    main()
