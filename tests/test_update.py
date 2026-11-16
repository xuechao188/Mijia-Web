#!/usr/bin/env python3
"""在线升级机制回归。

覆盖：版本比较、仓库地址解析、资产挑选、zip-slip 防护、备份/回滚、
五个接口的守卫与行为，以及前端入口/文案的静态不变量。
全程不连 GitHub、不改真实程序目录——下载与解压用打桩或隔离临时目录。
"""
import io
import os
import sys
import tempfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from app import create_app  # noqa: E402
from services import updater as U  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    ok_n[0] += 1
    if not cond:
        raise AssertionError(msg)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 1. 版本比较
ok(U.version_tuple("v0.2.0") == (0, 2, 0), "v 前缀被剥离")
ok(U.version_tuple("0.2.1-beta.1") == (0, 2, 1), "预发布标记忽略，取前三段数字")
ok(U.version_tuple("1.2") == (1, 2, 0), "缺段补零")
ok(U.is_newer("0.2.0", "0.1.0"), "小版本更新判定")
ok(U.is_newer("0.1.1", "0.1.0"), "补丁更新判定")
ok(U.is_newer("1.0.0", "0.9.9"), "主版本更新判定")
ok(not U.is_newer("0.1.0", "0.1.0"), "同版本不算更新")
ok(not U.is_newer("0.1.0", "0.2.0"), "旧版本不算更新")
ok(not U.is_newer("0.0.9", "0.1.0"), "更小版本不算更新")

# ---------------------------------------------------------------- 2. 仓库地址
old_repo, old_api, old_home = config.UPDATE_REPO, config.UPDATE_API, config.UPDATE_HOMEPAGE
try:
    config.UPDATE_REPO = ""
    config.UPDATE_HOMEPAGE = ""
    ok(not U.configured(), "空仓库视为未配置")
    ok(U.repo_homepage() == "", "未配置时主页为空")
    config.UPDATE_REPO = "owner/repo"
    ok(U.configured(), "owner/repo 视为已配置")
    ok(U.repo_homepage() == "https://github.com/owner/repo", "主页按仓库拼出")
    config.UPDATE_HOMEPAGE = "https://git.example.com/x"
    ok(U.repo_homepage() == "https://git.example.com/x", "自定义主页优先")
    for bad in ["owner", "has space/repo", "/repo", "owner/"]:
        config.UPDATE_REPO = bad
        ok(not U.configured(), "非法仓库格式被拒：%r" % bad)
finally:
    config.UPDATE_REPO, config.UPDATE_API, config.UPDATE_HOMEPAGE = old_repo, old_api, old_home

# ---------------------------------------------------------------- 3. 资产挑选
rel = {"assets": [
    {"name": "source.tar.gz", "size": 1},
    {"name": "Mijia-Web-0.2.0.zip", "size": 100, "browser_download_url": "https://github.com/x"},
]}
a = U._pick_asset(rel, "0.2.0")
ok(a["name"] == "Mijia-Web-0.2.0.zip", "精确匹配版本号资产")
rel2 = {"assets": [{"name": "Mijia-Web-0.3.0.zip", "size": 1}]}
ok(U._pick_asset(rel2, "0.2.0")["name"] == "Mijia-Web-0.3.0.zip", "回退到同前缀 zip")
try:
    U._pick_asset({"assets": [{"name": "readme.md"}]}, "0.2.0")
    ok(False, "无升级包应报错")
except U.UpdateError:
    ok(True, "无升级包资产被拒绝")

# ---------------------------------------------------------------- 4. 白名单
for p in ["app.py", "config.py", "routes/auth.py", "services/updater.py",
          "static/vue/assets/index-abc.js", "web/src/App.vue",
          "web/package.json", "web/vite.config.ts", "README.md", "LICENSE"]:
    ok(U._is_allowed(p), "允许更新 %s" % p)
for p in ["../etc/passwd", "/etc/passwd", "C:/x", "mi.token",
          "web/node_modules/x.js", ".venv/bin/python", "services/__pycache__/x.pyc",
          "data/mi.token", "config.py/../../x", "updates/state.json",
          "web/src/../../secret"]:
    ok(not U._is_allowed(p), "拒绝更新 %s" % p)

# ---------------------------------------------------------------- 5. zip 安全
def make_zip(entries):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, data in entries:
            z.writestr(name, data)
    return buf.getvalue()


good_zip = make_zip([("services/demo.py", b"print(1)"),
                     ("web/src/X.vue", b"<template/>")])
with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
    tf.write(good_zip)
    good_path = tf.name
try:
    files = U.inspect_zip(good_path)
    ok(set(files) == {"services/demo.py", "web/src/X.vue"}, "合法升级包列出正确文件")
finally:
    os.remove(good_path)

bad_cases = [
    ("zip-slip", [("../../etc/passwd", b"x")]),
    ("绝对路径", [("/etc/passwd", b"x")]),
    ("命中 token", [("mi.token", b"x")]),
    ("写node_modules", [("web/node_modules/evil.js", b"x")]),
    ("写缓存", [("services/__pycache__/x.pyc", b"x")]),
    ("不在白名单", [("secret.txt", b"x")]),
]
for label, entries in bad_cases:
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
        tf.write(make_zip(entries))
        p = tf.name
    try:
        try:
            U.inspect_zip(p)
            ok(False, "%s 应被拒绝" % label)
        except U.UpdateError:
            ok(True, "%s 被拒绝" % label)
    finally:
        os.remove(p)

# 损坏 zip
with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tf:
    tf.write(b"not a zip")
    p = tf.name
try:
    try:
        U.inspect_zip(p)
        ok(False, "损坏 zip 应被拒绝")
    except U.UpdateError:
        ok(True, "损坏 zip 被拒绝")
finally:
    os.remove(p)

# ---------------------------------------------------------------- 6. 下载 URL 校验
old_asset_prefix = config.UPDATE_ASSET_PREFIX
try:
    for bad in ["http://github.com/x.zip", "https://evil.com/x.zip",
                "https://github.com.evil.com/x.zip",
                "https://githubusercontent.com.evil.com/x.zip"]:
        try:
            U._safe_download(bad, os.path.join(tempfile.gettempdir(), "never.zip"))
            ok(False, "拒绝不安全下载地址 %s" % bad)
        except U.UpdateError:
            ok(True, "拒绝不安全下载地址 %s" % bad)
finally:
    config.UPDATE_ASSET_PREFIX = old_asset_prefix

# 6b. GitHub 资产 CDN 域名放行（真实下载会 302 到这些主机）
for good in ["github.com", "objects.githubusercontent.com",
             "github-releases.githubusercontent.com",
             "release-assets.githubusercontent.com", "codeload.github.com"]:
    ok(U._download_host_ok(good), "放行 GitHub 资产域名 %s" % good)
for bad in ["evil.com", "github.com.evil.com", "notgithubusercontent.com",
            "githubusercontent.com.evil.com", ""]:
    ok(not U._download_host_ok(bad), "拒绝仿冒域名 %s" % bad)
ok(U._download_host_ok("api.github.com", "api.github.com"), "放行自建 API 主机")

# ---------------------------------------------------------------- 7. HTTP 接口
config.UPDATE_REPO = ""   # 测「未配置」分支
client = create_app().test_client()

r = client.get("/api/update/info")
ok(r.status_code == 200, "info 200")
info = r.get_json()
ok(info["ok"] and info["version"] == config.VERSION, "info 返回当前版本")
ok(info["configured"] is False, "未配置时 configured=false")
ok(info["name"] == config.APP_NAME_CN, "info 返回应用名")
ok("backups" in info and isinstance(info["backups"], list), "info 带备份列表")

r = client.post("/api/update/check")
ok(r.status_code == 200, "check 200")
ok(r.get_json()["ok"] is False and "尚未配置" in r.get_json()["error"],
   "未配置时 check 给出友好提示")

for get_only in ["/api/update/check", "/api/update/apply",
                 "/api/update/rollback", "/api/update/restart"]:
    ok(client.get(get_only).status_code == 405, "写接口 %s 拒绝 GET" % get_only)

r = client.post("/api/update/apply")
ok(r.status_code == 400 and r.get_json()["ok"] is False, "未配置时 apply 返回 400")

# ping 仍正常，版本号在 info 单独给
ping = client.get("/api/ping").get_json()
ok(ping["version"] == config.VERSION, "ping 仍带版本号")

# ---------------------------------------------------------------- 8. 前端不变量
app_src = read("web/src/App.vue")
ok("AboutDialog" in app_src, "App.vue 引入关于弹窗")
ok("top-version" in app_src, "顶栏有版本号按钮")
ok("openAbout" in app_src, "版本号按钮有点击处理")
ok("appVersion" in app_src, "版本号从后端读取")

about = read("web/src/components/AboutDialog.vue")
for needle in ["当前版本", "项目地址", "检测新版本", "下载并升级",
               "回滚到升级前", "useUpdateStore"]:
    ok(needle in about, "关于弹窗含文案/store：%s" % needle)
ok("has_update" in about, "仅在有更新时显示升级按钮")

store = read("web/src/stores/update.ts")
for ep in ["/api/update/info", "/api/update/check", "/api/update/apply",
           "/api/update/rollback", "/api/update/restart"]:
    ok(ep in store, "store 封装接口 %s" % ep)

build_index = read("static/vue/index.html")
ok("static/vue/assets/index-" in build_index, "构建产物已入库（index.html 引用带 hash 资源）")

# ---------------------------------------------------------------- 9. 配置与文档
cfg = read("config.py")
for key in ["UPDATE_REPO", "UPDATE_API", "UPDATE_ASSET_PREFIX",
            "UPDATE_MAX_BYTES", "UPDATE_BACKUP_KEEP", "UPDATE_AUTO_RESTART"]:
    ok(key in cfg, "config.py 含升级配置 %s" % key)

bp = read("app.py")
ok("routes.update" in bp and "update_bp" in bp, "app.py 注册升级蓝图")

print("update 测试通过：%d 项" % ok_n[0])
