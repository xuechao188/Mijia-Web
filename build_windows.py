#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建 Windows 绿色版（跨平台可运行：Windows / macOS / Linux 均可执行）

用法：
    python build_windows.py

输出：
    dist/米家Web版-Windows-v<版本号>.zip

说明：
    把打包流程固化为一个脚本，避免手工命令遗漏。其中 python313._pth 的第 2 行
    必须是 ".."（指向应用根目录），不能是 "." —— 因为 Windows 的 Python 嵌入版
    会把 "." 解析为 python.exe 所在的 python/ 目录，导致 config.py 等顶层模块
    不在搜索路径里，服务启动时报 ModuleNotFoundError。
"""
import os
import re
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

# ---------------------------------------------------------------- 配置
HERE = Path(__file__).resolve().parent
BUILD = HERE / "build"          # 临时构建目录（每次重建）
DIST = HERE / "dist"            # 输出目录
CACHE = HERE / ".build-cache"   # 下载缓存：embed 运行时 + wheel，跨次复用
PY_VER = "3.13.12"              # Windows embeddable Python 版本
EMBED_URL = (
    "https://www.python.org/ftp/python/%s/python-%s-embed-amd64.zip"
    % (PY_VER, PY_VER)
)

# 复制到绿色版的顶层源码文件/目录
SRC_ITEMS = [
    "app.py", "cli.py", "config.py", "run.py", "logx.py",
    "requirements.txt", "README.md", "LICENSE",
    "routes", "services", "static", "docs",
]

# python313._pth 内容 —— 关键：第 2 行用 ".." 指向应用根目录
# （历史上这里误写成 "."，导致绿色版无法启动，务必不要改回 "."）
PTH_CONTENT = (
    "python313.zip\n"
    "..\n"
    "Lib\\site-packages\n"
    "import site\n"
)

# ---------------------------------------------------------------- 工具
def write_crlf(path, text, encoding="utf-8", bom=False):
    """按 Windows 约定写文本：CRLF 换行。

    关键：bat 批处理若用纯 LF 换行，cmd.exe 解析 `if (...)` 多行块会失败，
    表现为双击后窗口一闪而过 / 无法启动。因此所有 Windows 文本统一 CRLF。
    """
    data = text.replace("\r\n", "\n").replace("\n", "\r\n").encode(encoding)
    if bom:
        data = b"\xef\xbb\xbf" + data
    path.write_bytes(data)


def log(msg):
    print("[build] " + msg, flush=True)


def read_version():
    """从 config.py 读取 VERSION，避免版本号多处维护。"""
    text = (HERE / "config.py").read_text(encoding="utf-8")
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not m:
        raise RuntimeError("无法从 config.py 解析 VERSION")
    return m.group(1)


def download(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        log("复用已下载：%s（%d 字节）" % (dest.name, dest.stat().st_size))
        return
    log("下载 %s" % url)
    with urllib.request.urlopen(url, timeout=180) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    log("下载完成：%s（%d 字节）" % (dest.name, dest.stat().st_size))


def run_pip_download(wheels_dir):
    """下载可在 Windows x64 上使用的依赖 wheel（含 C 扩展）。

    每次都执行 pip download：pip 会跳过已存在且满足的 wheel，只补下新增/变更的
    依赖（例如 requirements.txt 新增 certifi）。不能简单用"目录非空就跳过"，
    否则依赖清单变化后新包会缺依赖。
    """
    wheels_dir.mkdir(parents=True, exist_ok=True)
    log("解析 Windows 依赖 wheel（win_amd64）...")
    cmd = [
        sys.executable, "-m", "pip", "download",
        "--platform", "win_amd64",
        "--python-version", "3.13",
        "--only-binary=:all:",
        "--dest", str(wheels_dir),
        "-r", str(HERE / "requirements.txt"),
    ]
    subprocess.check_call(cmd)
    log("依赖 wheel 就绪（目录共 %d 个）" % len(list(wheels_dir.glob("*.whl"))))


def extract_wheels(wheels_dir, site_dir):
    site_dir.mkdir(parents=True, exist_ok=True)
    wheels = sorted(wheels_dir.glob("*.whl"))
    if not wheels:
        raise RuntimeError("没有找到任何 wheel 文件")
    for w in wheels:
        with zipfile.ZipFile(w) as z:
            z.extractall(site_dir)
    log("已解压 %d 个 wheel 到 site-packages" % len(wheels))


def copy_sources(app):
    for item in SRC_ITEMS:
        src, dst = HERE / item, app / item
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True)
        elif src.is_file():
            shutil.copy2(src, dst)
        else:
            raise RuntimeError("缺少待打包项：%s" % src)
    # web：复制除 node_modules 外的全部内容（有则复制，无则跳过）
    web_src, web_dst = HERE / "web", app / "web"
    web_dst.mkdir(parents=True, exist_ok=True)
    for child in web_src.iterdir():
        if child.name == "node_modules":
            continue
        if child.is_dir():
            shutil.copytree(child, web_dst / child.name, dirs_exist_ok=True)
        else:
            shutil.copy2(child, web_dst / child.name)
    # 清理开发期产物，避免混入打包
    for pc in app.rglob("__pycache__"):
        shutil.rmtree(pc, ignore_errors=True)
    for pyc in app.rglob("*.pyc"):
        pyc.unlink(missing_ok=True)
    log("项目源码复制完成")


def write_launchers(app):
    # 主推：启动.bat
    # 【编码关键】bat 一律用 GBK(CP936) 编码写入，且不做 chcp 65001 切换。
    # 中文 Windows 的 cmd.exe 原生按系统 ANSI 代码页(936/GBK)读取 bat，逐字节解析稳定；
    # 若用 UTF-8 + chcp 65001，cmd 在解析含中文的长行时会发生行指针错位，吞掉行首的
    # "echo "，把中文提示当成命令执行，报 "'xxx' is not recognized..."。
    # 官方实测：同一份脚本，UTF-8 编码报错，改成 GBK 编码后中文全部正常、无任何报错。
    # 另：绝不使用 `if (...)` 多行括号块 + 中文，改用 goto 标签式单行判断；
    # 中文只出现在 echo / title 里，绝不进入含括号或引号的解析敏感行。
    # 打开浏览器已整合进本文件：ping 延时等服务就绪后直接用 start 打开网址。
    bat = (
        "@echo off\n"
        "title 米家Web版\n"
        'cd /d "%~dp0"\n'
        "echo ============================================\n"
        "echo   米家Web版 正在启动...\n"
        "echo ============================================\n"
        "echo.\n"
        'if not exist "%~dp0python\\python.exe" goto :NOPY\n'
        "echo [1/3] 检查 Python 运行环境...\n"
        '"%~dp0python\\python.exe" -c "import sys" >nul 2>&1\n'
        "if errorlevel 1 goto :PYFAIL\n"
        "echo 运行环境检查通过。\n"
        "echo [2/3] 检查依赖组件...\n"
        '"%~dp0python\\python.exe" -c "import flask,waitress,aiohttp,miservice" >nul 2>&1\n'
        "if errorlevel 1 goto :DEPFAIL\n"
        "echo 依赖组件检查通过。\n"
        "echo [3/3] 正在后台启动服务...\n"
        "echo 访问地址: http://127.0.0.1:8765\n"
        "echo 浏览器将自动打开；若没有，请手动复制上面的地址到浏览器。\n"
        "echo.\n"
        "set MIHOME_NO_BROWSER=1\n"
        'start "" /D "%~dp0" "%~dp0python\\pythonw.exe" "%~dp0run.py"\n'
        "echo 正在等待服务就绪并打开浏览器...\n"
        "ping -n 4 127.0.0.1 >nul 2>nul\n"
        'start "" "http://127.0.0.1:8765"\n'
        "echo.\n"
        "echo [完成] 服务已在后台运行。\n"
        "echo 你可以关闭此窗口，服务不会停止。\n"
        'echo 需要停止服务时，请双击 停止.bat。\n'
        "echo.\n"
        "echo 按任意键关闭此窗口...\n"
        "pause >nul\n"
        "exit /b 0\n"
        "\n"
        ":NOPY\n"
        "echo [错误] 找不到 python\\python.exe。\n"
        "echo 请保持 python 文件夹与本文件在同一目录。\n"
        "echo 按任意键关闭此窗口...\n"
        "pause >nul\n"
        "exit /b 1\n"
        "\n"
        ":PYFAIL\n"
        "echo [错误] Python 无法启动，可能缺少系统运行库。\n"
        "echo 建议安装 Visual C++ 2015-2022 运行库 (x64)。\n"
        "echo 按任意键关闭此窗口...\n"
        "pause >nul\n"
        "exit /b 1\n"
        "\n"
        ":DEPFAIL\n"
        "echo [错误] 依赖组件加载失败，详见上面的提示。\n"
        "echo 按任意键关闭此窗口...\n"
        "pause >nul\n"
        "exit /b 1\n"
    )
    write_crlf(app / "启动.bat", bat, encoding="gbk")

    # 停止.bat：按端口 8765 精准定位服务进程并结束。
    # 关键：netstat 的监听状态在部分 Windows 上不显示 LISTENING（可能显示 ESTABLISHED），
    # 因此不能用 "LISTENING" 过滤。改为：本地地址列(tokens=2)恰为 127.0.0.1:8765 且 PID(tokens=5) 非 0。
    # 该 for 行含引号/括号，必须保持纯 ASCII；中文仅出现在 echo / title 里。
    stop = (
        "@echo off\n"
        "title 停止 米家Web版\n"
        "echo ============================================\n"
        "echo   正在停止 米家Web版 ...\n"
        "echo ============================================\n"
        "echo.\n"
        "set PID=\n"
        'for /f "tokens=2,5" %%a in (\'netstat -ano ^| findstr /C:"127.0.0.1:8765"\') do if "%%a"=="127.0.0.1:8765" if not "%%b"=="0" set PID=%%b\n'
        'if "%PID%"=="" goto :NOTRUNNING\n'
        "echo 已找到服务进程 PID=%PID%，正在结束...\n"
        "taskkill /PID %PID% /F >nul 2>&1\n"
        "if errorlevel 1 goto :KILLFAIL\n"
        "echo [完成] 服务已停止，可以关闭此窗口。\n"
        "goto :END\n"
        ":NOTRUNNING\n"
        "echo [提示] 米家Web版 当前未运行（8765 端口空闲）。\n"
        "goto :END\n"
        ":KILLFAIL\n"
        "echo [错误] 无法结束进程 PID=%PID%，请在任务管理器中手动结束。\n"
        "goto :END\n"
        ":END\n"
        "echo.\n"
        "echo 按任意键关闭此窗口...\n"
        "pause >nul\n"
        "exit /b 0\n"
    )
    write_crlf(app / "停止.bat", stop, encoding="gbk")

    # 启动.vbs 已废弃：VBS/WSH 易被安全软件拦截且出错无提示，统一用 启动.bat。

    # 使用说明：UTF-8 BOM，便于 Windows 记事本正确显示中文
    readme = (
        "米家Web版 - Windows 绿色版\n"
        "================================\n\n"
        "【启动】\n"
        "双击「启动.bat」。会弹出一个黑色窗口，依次显示：\n"
        "  [1/3] 检查 Python 运行环境\n"
        "  [2/3] 检查依赖组件\n"
        "  [3/3] 正在后台启动服务\n"
        '看到 "[完成] 服务已在后台运行" 且浏览器自动打开即成功。\n'
        "服务在后台运行，关闭这个黑色窗口也不影响，可放心关掉。\n\n"
        "【停止服务】\n"
        "双击「停止.bat」，看到 \"[完成] 服务已停止\" 即已停止。\n"
        "它按端口精准结束服务进程，不会误伤其他程序。\n"
        "若服务本就没运行，会提示 \"当前未运行\"，属正常。\n"
        "注意：后台模式下，关闭启动窗口不会停止服务，必须用「停止.bat」。\n\n"
        "【常见问题】\n"
        '1. 窗口停在 "[1/3] 检查 Python 运行环境" 后出现 "Press any key"：\n'
        "   把整个窗口截图发回（这是异常，正常应继续到 [3/3]）。\n\n"
        '2. 看到 "[错误]" 开头的提示：\n'
        "   把窗口里显示的提示截图发回，不要点掉。\n\n"
        "3. 浏览器没自动打开：\n"
        "   手动打开浏览器，在地址栏输入 http://127.0.0.1:8765\n\n"
        "4. Windows 防火墙提示：\n"
        '   点"允许访问"。程序只监听本机 8765 端口，不对外暴露。\n\n'
        "5. 杀毒软件报毒/拦截：\n"
        '   这是 Python 运行环境和启动脚本被误报，选择"允许/信任"即可。\n\n'
        "【登录】\n"
        '首次打开点"登录"，用手机米家 App 扫码即可。登录态保存在用户目录\n'
        "(%LOCALAPPDATA%\\Mijia-Web)，不写本文件夹，更新/重装不会掉登录。\n\n"
        "【在线升级】\n"
        "右上角点版本号 → 关于应用 → 检测新版本，有新版本点\"下载并升级\"。\n"
        "升级只替换源码文件，你的登录态和数据不受影响。\n\n"
        "【移动 / 删除】\n"
        "移动：整个文件夹可拷到任意位置或 U 盘，保持 python 文件夹在一起。\n"
        "删除：不需要时直接删整个文件夹。\n"
    )
    write_crlf(app / "使用说明.txt", readme, encoding="utf-8", bom=True)
    log("启动器与使用说明写入完成（CRLF 换行）")


def make_zip(app, out_zip):
    """用 Python zipfile 打包，确保 UTF-8 文件名标志正确（中文不乱码）。"""
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                z.write(path, path.relative_to(app.parent))
    log("打包完成：%s（%d 字节）" % (out_zip.name, out_zip.stat().st_size))


def main():
    version = read_version()
    log("版本：%s" % version)
    app_name = "米家Web版-Windows-v%s" % version

    if BUILD.exists():
        shutil.rmtree(BUILD)
    (BUILD / "python").mkdir(parents=True)
    DIST.mkdir(parents=True, exist_ok=True)

    app = BUILD / app_name
    app.mkdir(parents=True)

    # 1) 下载并解压 Windows embeddable Python（运行时放缓存，避免每次重下）
    CACHE.mkdir(parents=True, exist_ok=True)
    embed_zip = CACHE / "python-embed.zip"
    download(EMBED_URL, embed_zip)
    with zipfile.ZipFile(embed_zip) as z:
        z.extractall(BUILD / "python")

    # 2) 写 python313._pth
    pth = BUILD / "python" / "python313._pth"
    pth.write_bytes(PTH_CONTENT.replace("\n", "\r\n").encode("ascii"))
    log("写入 python313._pth（第 2 行为 ..，指向应用根目录）")

    # 3) 下载依赖 wheel（放缓存）并解压到 site-packages
    wheels = CACHE / "wheels"
    run_pip_download(wheels)
    extract_wheels(wheels, BUILD / "python" / "Lib" / "site-packages")

    # 4) 组装应用目录
    shutil.copytree(BUILD / "python", app / "python")
    copy_sources(app)
    write_launchers(app)

    # 5) 打包
    out_zip = DIST / ("%s.zip" % app_name)
    make_zip(app, out_zip)

    log("=" * 50)
    log("全部完成：%s" % out_zip)
    log("=" * 50)


if __name__ == "__main__":
    main()
