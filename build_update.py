#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
构建「在线升级包」：dist/Mijia-Web-<版本号>.zip

与 Windows / macOS 完整安装包不同，升级包供应用内升级机制使用：
  - zip 内路径是相对程序根目录的裸路径（config.py / routes/xxx.py / static/...），
    没有中文顶层目录 —— 因为 updater.apply() 会按相对路径直接覆盖程序目录。
  - 只包含 services/updater.py 白名单内的文件；token / 缓存 / .git / .venv /
    node_modules / docs 等一律不含。
  - 白名单函数直接复用 updater._is_allowed（单一真相源），生成后调用
    updater.inspect_zip 自校验，保证上传的包一定能通过升级器的结构校验。

用法：
    python build_update.py

输出：
    dist/Mijia-Web-<版本号>.zip   并在末尾打印 sha256（对照 GitHub 资产 digest）
"""
import hashlib
import re
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
sys.path.insert(0, str(HERE))

from services import updater  # noqa: E402  复用白名单（单一真相源）


def log(msg):
    print("[update] " + msg, flush=True)


def read_version():
    text = (HERE / "config.py").read_text(encoding="utf-8")
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', text, re.M)
    if not m:
        raise RuntimeError("无法从 config.py 解析 VERSION")
    return m.group(1)


def collect_files():
    """按 updater 的白名单收集待打包文件，返回 (绝对路径, zip内相对路径) 列表。"""
    picked = []
    for prefix in updater.ALLOWED_PREFIXES:
        base = HERE / prefix
        if prefix.endswith("/"):
            if not base.is_dir():
                continue
            for p in sorted(base.rglob("*")):
                if not p.is_file():
                    continue
                rel = p.relative_to(HERE).as_posix()
                if p.suffix == ".pyc" or "__pycache__" in rel:
                    continue
                if updater._is_allowed(rel):
                    picked.append((p, rel))
        else:
            if base.is_file() and updater._is_allowed(prefix):
                picked.append((base, prefix))
    # 去重并保持顺序
    seen = set()
    out = []
    for abs_p, rel in picked:
        if rel not in seen:
            seen.add(rel)
            out.append((abs_p, rel))
    return out


def main():
    version = read_version()
    DIST.mkdir(parents=True, exist_ok=True)
    out_zip = DIST / ("Mijia-Web-%s.zip" % version)

    files = collect_files()
    log("白名单命中 %d 个文件" % len(files))
    if not files:
        raise RuntimeError("没有收集到任何可升级文件")

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for abs_p, rel in files:
            z.write(abs_p, rel)

    # 自校验：必须能通过升级器的结构校验
    listed = updater.inspect_zip(str(out_zip))
    log("inspect_zip 校验通过：%d 个文件" % len(listed))

    # 关键文件断言（防止白名单误配导致升级包缺斤少两）
    must = {
        "app.py", "config.py", "run.py", "logx.py", "requirements.txt",
        "routes/update.py", "services/updater.py",
        "static/vue/index.html", "web/src/App.vue", "web/src/stores/devices.ts",
    }
    missing = must - set(listed)
    if missing:
        raise RuntimeError("升级包缺少关键文件：%s" % sorted(missing))

    # 确认包内 config.py 就是本次版本号
    with zipfile.ZipFile(out_zip) as z:
        cfg = z.read("config.py").decode("utf-8")
    m = re.search(r'^VERSION\s*=\s*["\']([^"\']+)["\']', cfg, re.M)
    if not m or m.group(1) != version:
        raise RuntimeError("升级包内 config.py 版本不符：%s" % (m.group(1) if m else "缺失"))

    sha = hashlib.sha256(out_zip.read_bytes()).hexdigest()
    log("打包完成：%s（%d 字节）" % (out_zip.name, out_zip.stat().st_size))
    log("sha256:%s" % sha)


if __name__ == "__main__":
    main()
