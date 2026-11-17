#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 macOS 通用版（一个 zip 同时支持 Intel 与 Apple Silicon）

用法：
    python build_macos.py

输出：
    dist/米家Web版-macOS-v<版本号>.zip

设计要点：
  1. 包内不带 Python —— 首次启动时检测系统 Python(3.10~3.13)，
     没有则按本机架构下载 python-build-standalone 的 install_only 包，
     解压到应用内 runtime/ 并校验 SHA256，全程无需 sudo、无需管理员权限。
  2. 所有运行期文件（venv / 日志 / pid）都在应用目录内；
     登录 token / 缓存 / 数据库按 config.py 落到 ~/Library/Application Support/Mijia-Web。
  3. 启动脚本用 bash + LF 换行 + UTF-8；.command 显式置 0755。
"""
import os
import re
import shutil
import stat
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"
DIST = HERE / "dist"

# python-build-standalone release 20261110 / CPython 3.13.18
PY_TAG = "20261110"
PY_VER = "3.13.18"
PY_RELEASE = "https://github.com/astral-sh/python-build-standalone/releases/download/" + PY_TAG
PY_ARTIFACTS = {
    "arm64": (
        "cpython-%s%%2B%s-aarch64-apple-darwin-install_only.tar.gz" % (PY_VER, PY_TAG),
        "1afd3983237c2a10277345f235be730e9cb49a123e0574ed252dbf3a841a24e4",
    ),
    "x86_64": (
        "cpython-%s%%2B%s-x86_64-apple-darwin-install_only.tar.gz" % (PY_VER, PY_TAG),
        "a46bcdeecd28ba253522b321dcb3806da1b0ff581479fc1d27e9613e3ac44764",
    ),
}

SRC_ITEMS = [
    "app.py", "cli.py", "config.py", "run.py", "logx.py",
    "requirements.txt", "README.md", "LICENSE",
    "routes", "services", "static", "docs",
]


def log(msg):
    print("[build-macos] " + msg, flush=True)


def read_version():
    text = (HERE / "config.py").read_text(encoding="utf-8")
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not m:
        raise RuntimeError("无法从 config.py 解析 VERSION")
    return m.group(1)


def copy_sources(app):
    for item in SRC_ITEMS:
        src, dst = HERE / item, app / item
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.is_file():
            shutil.copy2(src, dst)
        else:
            raise RuntimeError("缺少待打包项：%s" % src)
    web_src, web_dst = HERE / "web", app / "web"
    web_dst.mkdir(parents=True, exist_ok=True)
    for child in web_src.iterdir():
        if child.name == "node_modules":
            continue
        if child.is_dir():
            shutil.copytree(child, web_dst / child.name, dirs_exist_ok=True)
        else:
            shutil.copy2(child, web_dst / child.name)
    for pc in app.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)
    for pyc in app.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)
    log("项目源码复制完成")


START_SH = r'''#!/bin/bash
# 米家Web版 macOS 启动器（双击运行）
# 全自动：检测 Python -> 缺失则按架构下载免安装版 -> 建 venv -> 装依赖 -> 启服务 -> 开浏览器
set -u
cd "$(dirname "$0")" || exit 1
APP="$(pwd)"

echo "============================================"
echo "  米家Web版 正在启动..."
echo "============================================"
echo ""

PY=""
BASE_PY=""

# ---------- 1) 优先复用已建好的运行环境 ----------
if [ -x "$APP/.venv/bin/python3" ]; then
  PY="$APP/.venv/bin/python3"
  echo "[1/4] 复用已有运行环境"
else
  echo "[1/4] 检测系统 Python（支持 3.10 ~ 3.13）..."
  SYS_PY=""
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      nums=$("$c" -c 'import sys;print(sys.version_info[0],sys.version_info[1])' 2>/dev/null)
      set -- $nums
      maj=${1:-0}; min=${2:-0}
      if [ "$maj" = "3" ] && [ "$min" -ge 10 ] 2>/dev/null && [ "$min" -le 13 ] 2>/dev/null; then
        SYS_PY="$c"
        break
      fi
    fi
  done

  if [ -n "$SYS_PY" ]; then
    echo "  已找到：$("$SYS_PY" --version 2>&1)"
    BASE_PY="$SYS_PY"
  else
    echo "  未找到合适的 Python，将自动下载免安装版（约 25MB，仅首次）..."
    ARCH="$(uname -m)"
    case "$ARCH" in
      arm64|aarch64) FILE="PY_ARM_NAME"; SHA="PY_ARM_SHA" ;;
      x86_64|amd64)  FILE="PY_X64_NAME"; SHA="PY_X64_SHA" ;;
      *) echo "[错误] 不支持的 CPU 架构：$ARCH"; echo "按任意键关闭..."; read -r -n 1; exit 1 ;;
    esac
    URL="PY_RELEASE/$FILE"
    mkdir -p "$APP/runtime/_dl"
    echo "  正在下载：$FILE"
    curl -fL --retry 3 --connect-timeout 20 "$URL" -o "$APP/runtime/_dl/python.tar.gz"
    if [ $? -ne 0 ]; then
      echo "[错误] 下载失败。请检查网络后重试，或手动下载放到 runtime/python/（见使用说明）。"
      echo "按任意键关闭..."; read -r -n 1; exit 1
    fi
    ACTUAL="$(shasum -a 256 "$APP/runtime/_dl/python.tar.gz" | awk '{print $1}')"
    if [ "$ACTUAL" != "$SHA" ]; then
      echo "[错误] 下载文件校验失败（可能被网络劫持），已停止。"
      echo "按任意键关闭..."; read -r -n 1; exit 1
    fi
    echo "  下载并校验通过，正在解压..."
    tar -xzf "$APP/runtime/_dl/python.tar.gz" -C "$APP/runtime"
    rm -rf "$APP/runtime/_dl"
    BASE_PY="$APP/runtime/python/bin/python3"
    chmod +x "$BASE_PY" 2>/dev/null
    # 部分系统对下载的可执行文件有签名要求，做一次 ad-hoc 签名（失败不影响）
    codesign --force --deep --sign - "$BASE_PY" >/dev/null 2>&1 || true
    echo "  免安装 Python 就绪：$("$BASE_PY" --version 2>&1)"
  fi

  echo "[2/4] 创建独立运行环境（.venv）..."
  "$BASE_PY" -m venv "$APP/.venv"
  if [ ! -x "$APP/.venv/bin/python3" ]; then
    echo "[错误] 运行环境创建失败。"
    echo "按任意键关闭..."; read -r -n 1; exit 1
  fi
  PY="$APP/.venv/bin/python3"

  echo "[3/4] 安装依赖（首次需要几分钟，请耐心等待）..."
  "$APP/.venv/bin/pip" install --disable-pip-version-check -r "$APP/requirements.txt" \
      -i https://pypi.tuna.tsinghua.edu.cn/simple
  if [ $? -ne 0 ]; then
    echo "  镜像源安装失败，改用官方源重试..."
    "$APP/.venv/bin/pip" install --disable-pip-version-check -r "$APP/requirements.txt"
  fi
fi

echo "[4/4] 启动服务..."
mkdir -p "$APP/logs"
nohup env MIHOME_NO_BROWSER=1 "$PY" "$APP/run.py" > "$APP/logs/server.log" 2>&1 &
echo $! > "$APP/logs/server.pid"

# 等待服务就绪（最多 20 秒）
OK=0
for i in $(seq 1 20); do
  if curl -fsS http://127.0.0.1:8765/api/ping >/dev/null 2>&1; then OK=1; break; fi
  sleep 1
done
if [ "$OK" = "1" ]; then
  open "http://127.0.0.1:8765" 2>/dev/null || true
  echo ""
  echo "[完成] 服务已在后台运行，浏览器已打开。"
  echo "访问地址：http://127.0.0.1:8765"
  echo "关闭此窗口不影响服务；停止服务请双击 停止.command"
else
  echo ""
  echo "[警告] 20 秒内未检测到服务就绪，请查看 logs/server.log 排查。"
  echo "常见原因：8765 端口被占用，或依赖未装全。"
fi
echo ""
echo "按回车键关闭此窗口..."
read -r
'''

STOP_SH = r'''#!/bin/bash
# 米家Web版 macOS 停止器（双击运行）
set -u
cd "$(dirname "$0")" || exit 1
APP="$(pwd)"

echo "============================================"
echo "  正在停止 米家Web版 ..."
echo "============================================"
echo ""

PID=""
if [ -f "$APP/logs/server.pid" ]; then
  PID="$(cat "$APP/logs/server.pid" 2>/dev/null)"
fi

# 端口兜底：用 lsof 找 8765 监听进程
PORTPID="$(lsof -nP -iTCP:8765 -sTCP:LISTEN -t 2>/dev/null | head -1)"

KILLED=0
if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
  kill "$PID" 2>/dev/null && KILLED=1
fi
if [ "$KILLED" = "0" ] && [ -n "$PORTPID" ] && [ "$PORTPID" != "$PID" ]; then
  kill "$PORTPID" 2>/dev/null && KILLED=1
fi

if [ "$KILLED" = "1" ]; then
  echo "[完成] 服务已停止。"
else
  echo "[提示] 米家Web版 当前未运行（8765 端口空闲）。"
fi
rm -f "$APP/logs/server.pid"
echo ""
echo "按回车键关闭此窗口..."
read -r
'''

README_TXT = """米家Web版 - macOS 版
================================

【首次使用前的准备（只需做一次）】
本压缩包从网络下载后，macOS 可能给脚本打上"隔离"标记，导致双击被拦截。
打开"终端"，把下面这行命令粘贴进去回车（把路径换成你解压后的实际位置）：

  xattr -cr "/你的路径/米家Web版-macOS-v{VER}"

之后即可正常双击。若双击仍提示"无法打开"，右键点击文件选"打开"。

【启动】
双击"启动.command"。首次会自动完成：
  1. 检测系统 Python（3.10~3.13），有就直接用；
  2. 没有则按你的芯片（Intel / Apple Silicon）自动下载免安装 Python，
     校验无误后解压到应用内 runtime/，不需要管理员权限、不装到系统；
  3. 创建 .venv 并安装依赖（这一步最慢，几分钟，之后就快了）；
  4. 启动服务并打开浏览器 http://127.0.0.1:8765

以后再启动，检测到 .venv 已存在，会直接跳到第 4 步，几秒即可。

【停止服务】
双击"停止.command"。它按 PID + 端口精准结束服务，不误伤其他程序。
也可以不停止：服务在后台运行，关掉启动窗口不影响。

【登录】
首次打开点"登录"，用手机米家 App 扫码即可，无需输密码。
登录态存在 ~/Library/Application Support/Mijia-Web，不写本文件夹，
更新 / 重装不会掉登录。

【在线升级】
右上角点版本号 → 关于应用 → 检测新版本，有新版本点"下载并升级"。
升级只替换源码文件，你的登录态和数据不受影响。

【放在哪个目录】
建议解压到"下载"或"文稿"等你有写权限的目录。
不要直接放到 /Applications（那是系统应用目录，可能没有写权限，
会导致 .venv 和日志无法创建）。

【删除 / 移动】
移动：整个文件夹可拷到任意位置，保持各文件在一起。
删除：不需要时直接删整个文件夹即可（登录数据在系统用户目录，
如需一并清除，删除 ~/Library/Application Support/Mijia-Web）。

【常见问题】
1. 启动时卡在"安装依赖"很久：
   首次安装依赖需要几分钟，属正常。若失败会自动改用官方源重试。

2. 提示"下载失败"：
   检查网络。也可手动下载对应架构的 install_only.tar.gz，
   解压后把里面的 python 文件夹放到本目录 runtime/python/，再重新双击启动。
   Intel 芯片选 x86_64，Apple Silicon 选 aarch64。

3. 浏览器没自动打开：
   手动打开浏览器，在地址栏输入 http://127.0.0.1:8765

4. 提示 8765 端口被占用：
   先双击"停止.command"，或关闭占用该端口的程序后重试。

5. 杀毒软件提示：
   这是 Python 运行环境和启动脚本被误报，选择"允许 / 信任"即可。
""".replace("{VER}", "{VERSION}")


def write_text(path, text, mode=None):
    path.write_text(text, encoding="utf-8")
    if mode is not None:
        path.chmod(mode)


def make_zip(app, out_zip):
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(app.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(app.parent)
            zi = zipfile.ZipInfo.from_file(path, rel)
            # 保留 .command 的可执行位，解压后双击即可运行
            if path.suffix == ".command":
                zi.external_attr = (stat.S_IFREG | 0o755) << 16
            else:
                zi.external_attr = (stat.S_IFREG | 0o644) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            with open(path, "rb") as f:
                z.writestr(zi, f.read())
    log("打包完成：%s（%d 字节）" % (out_zip.name, out_zip.stat().st_size))


def main():
    version = read_version()
    log("版本：%s" % version)
    app_name = "米家Web版-macOS-v%s" % version

    if BUILD.exists():
        shutil.rmtree(BUILD)
    DIST.mkdir(parents=True, exist_ok=True)
    app = BUILD / app_name
    app.mkdir(parents=True)

    copy_sources(app)

    start = (START_SH
             .replace("PY_ARM_NAME", PY_ARTIFACTS["arm64"][0])
             .replace("PY_ARM_SHA", PY_ARTIFACTS["arm64"][1])
             .replace("PY_X64_NAME", PY_ARTIFACTS["x86_64"][0])
             .replace("PY_X64_SHA", PY_ARTIFACTS["x86_64"][1])
             .replace("PY_RELEASE", PY_RELEASE))
    write_text(app / "启动.command", start, 0o755)
    write_text(app / "停止.command", STOP_SH, 0o755)
    write_text(app / "使用说明.txt", README_TXT.replace("{VERSION}", version), 0o644)
    log("启动器与使用说明写入完成（LF 换行 / UTF-8）")

    out_zip = DIST / ("%s.zip" % app_name)
    make_zip(app, out_zip)
    log("=" * 50)
    log("全部完成：%s" % out_zip)
    log("=" * 50)


if __name__ == "__main__":
    main()
