#!/usr/bin/env python3
"""公开发布 / 虚拟主机部署前的安全守卫回归。

全部用 Flask test_client，只测守卫本身，不连小米云端、不改真实数据目录。
"""
import base64
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from app import create_app  # noqa: E402
from services import devices as dev  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    ok_n[0] += 1
    if not cond:
        raise AssertionError(msg)


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


# ---- 1. 仓库卫生 ----
ignore = read(".gitignore")
for pat in [".venv/", "web/node_modules/", "_probe/", "mi.token",
            "*.db", "*.log", ".env", "device_id", "ir_keys.json"]:
    ok(pat in ignore, ".gitignore 排除 %s" % pat)
ok(config.HOST == "127.0.0.1" or os.environ.get("MIHOME_HOST"),
   "未显式配置时只绑回环")

# ---- 2. 同源守卫：本机照旧，域名需显式放行 ----
client = create_app().test_client()
URL = "/api/automations/preview"


def post(origin=None, auth=None):
    headers = {}
    if origin:
        headers["Origin"] = origin
    if auth:
        headers["Authorization"] = auth
    return client.post(URL, json={"scene_id": "x"}, headers=headers)


ok(post("http://127.0.0.1:8765").status_code != 403, "本机来源仍可写")
ok(post("http://localhost:8765").status_code != 403, "localhost 来源仍可写")
ok(post("https://evil.example").status_code == 403, "陌生域名写请求被拒")

old_env = os.environ.get("MIHOME_ALLOWED_ORIGINS")
os.environ["MIHOME_ALLOWED_ORIGINS"] = "mihome.example.com, www.example.com"
try:
    ok(config.allowed_origins() == config.LOCAL_HOSTS +
       ("mihome.example.com", "www.example.com"),
       "白名单包含域名且去掉空白")
    ok(post("https://mihome.example.com").status_code != 403,
       "配置过的域名可写")
    ok(post("https://www.example.com").status_code != 403,
       "多个域名都生效")
    ok(post("https://mihome.example.com.evil.com").status_code == 403,
       "后缀伪装不生效")
finally:
    if old_env is None:
        os.environ.pop("MIHOME_ALLOWED_ORIGINS", None)
    else:
        os.environ["MIHOME_ALLOWED_ORIGINS"] = old_env

# ---- 3. 可选 Basic 访问密码 ----
old_user, old_pwd = config.ACCESS_USER, config.ACCESS_PASSWORD
try:
    ok(client.get("/api/status").status_code == 200, "未配置密码时无需登录")
    config.ACCESS_USER, config.ACCESS_PASSWORD = "admin", "p@ss word"
    r = client.get("/api/status")
    ok(r.status_code == 401, "配置密码后未认证返回 401")
    ok("Basic" in r.headers.get("WWW-Authenticate", ""),
       "返回 WWW-Authenticate，浏览器会弹原生登录框")
    good = "Basic " + base64.b64encode(
        "admin:p@ss word".encode()).decode()
    bad = "Basic " + base64.b64encode("admin:wrong".encode()).decode()
    ok(client.get("/api/status", headers={"Authorization": good}).status_code == 200,
       "正确密码放行")
    ok(client.get("/api/status", headers={"Authorization": bad}).status_code == 401,
       "错误密码拒绝")
    ok(client.get("/api/status", headers={"Authorization": "Basic !!!"}).status_code == 401,
       "畸形 Authorization 不当成通过")
    ok(post("http://127.0.0.1:8765", good).status_code != 403,
       "认证通过后本机来源仍可写")
    ok(post("https://evil.example", good).status_code == 403,
       "密码不能绕过同源守卫")
finally:
    config.ACCESS_USER, config.ACCESS_PASSWORD = old_user, old_pwd

# ---- 3a. 写接口不接受 GET，杜绝 <img src> 之类的跨站触发 ----
for path in ["/api/set", "/api/switch", "/api/scenes/run", "/api/logout",
             "/api/otp", "/api/login", "/api/notices/read",
             "/api/notices/refresh", "/api/devices/refresh",
             "/api/login/qr/start"]:
    ok(client.get(path).status_code == 405, "%s 只接受 POST" % path)
ok(client.get("/api/status").status_code == 200, "只读状态接口仍是 GET")

# ---- 3b. token 文件权限 ----
if os.name != "nt":
    fd, tmp = tempfile.mkstemp(prefix="mi-token-")
    os.close(fd)
    os.chmod(tmp, 0o644)
    old_path = config.TOKEN_PATH
    try:
        config.TOKEN_PATH = tmp
        dev._harden_token_file()
        ok(os.stat(tmp).st_mode & 0o777 == 0o600, "登录后 token 收紧到 600")
    finally:
        config.TOKEN_PATH = old_path
        os.unlink(tmp)

# ---- 4. 响应安全头 ----
r = client.get("/")
for h, v in [("X-Content-Type-Options", "nosniff"),
             ("X-Frame-Options", "DENY"),
             ("Referrer-Policy", "no-referrer")]:
    ok(r.headers.get(h) == v, "响应带 %s: %s" % (h, v))

# ---- 5. 服务器部署时不开浏览器 ----
run_src = read("run.py")
ok("config.NO_BROWSER" in run_src and "if not config.NO_BROWSER" in run_src,
   "MIHOME_NO_BROWSER=1 时不自动开浏览器")

print("deploy_test: %d 项通过" % ok_n[0])
