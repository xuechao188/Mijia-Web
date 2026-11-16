"""在线升级服务：以 GitHub Releases 为版本源，检查 / 下载 / 应用新版本。

设计要点（改这里前先读）：
  1. 版本源只认 config.UPDATE_REPO 指向的仓库 latest release，资产名
     <UPDATE_ASSET_PREFIX><版本号>.zip（如 Mijia-Web-0.2.0.zip），不拼任意 URL。
  2. 只写白名单内的程序文件（前后端源码 + 构建产物），绝不碰数据目录、
     .git、.venv、node_modules、token/db/log；解压逐项做 zip-slip 校验。
  3. 覆盖前把将被替换的文件原样备份到数据目录 updates/backup/<时间戳>/，
     任一步失败即回滚；回滚点保留 UPDATE_BACKUP_KEEP 份。
  4. 下载走标准库 urllib，带体积上限与超时；先落临时文件再校验后改名。
  5. 本模块不主动重启进程——重启是由路由在响应发出后安排的（见 routes/update.py），
     这样单测能干净地断言行为而不真的把测试进程 exec 掉。
"""
import json
import os
import re
import shutil
import stat
import tempfile
import time
import urllib.error
import urllib.request
import zipfile

import config
import logx

log = logx.get("mihome.updater")

# 应用根目录（程序目录，升级写入的基准）
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 允许被升级覆盖的路径前缀（相对 APP_DIR，统一用 / 分隔）。
# 「前后端全部文件」= Python 源码 + 路由/服务 + 静态产物 + Vue 源码与构建配置。
ALLOWED_PREFIXES = (
    "app.py", "config.py", "cli.py", "run.py", "logx.py", "requirements.txt",
    "README.md", "LICENSE",
    "routes/", "services/", "static/", "web/src/",
    "web/package.json", "web/package-lock.json", "web/vite.config.ts",
    "web/tsconfig.json", "web/index.html",
)
# 即便落在白名单前缀里也绝不允许写的文件（数据与凭据)
DENY_NAMES = ("mi.token", "token.json", "device_id")
DENY_PARTS = ("__pycache__", ".git", ".venv", "node_modules", "updates")


# GitHub 官方下载/资产域名。Release 资产会 302 到 CDN，且 CDN 子域会变
# （历史上用过 objects./github-releases.，现又新增 release-assets.），
# 因此除精确主机外，额外放行 *.githubusercontent.com —— 该二级域为 GitHub
# 专有，第三方无法注册其子域，不会引入 github.com.evil.com 这类钓鱼风险。
GITHUB_DOWNLOAD_HOSTS = {
    "github.com",
    "codeload.github.com",
}
GITHUB_CDN_SUFFIX = ".githubusercontent.com"


def _download_host_ok(host: str, api_host: str = "") -> bool:
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    if host in GITHUB_DOWNLOAD_HOSTS or host == api_host:
        return True
    return host.endswith(GITHUB_CDN_SUFFIX)


class UpdateError(Exception):
    """升级过程中的可预期失败，消息可直接展示给用户。"""


# ---------------------------------------------------------------- 版本工具
def version_tuple(s: str) -> tuple:
    """把 'v0.2.0' / '0.2.1-beta.1' 归一成可比较的整数元组 (0,2,0)。

    只取前三段数字，预发布标记忽略——比较用；展示仍用原始 tag。
    """
    nums = re.findall(r"\d+", s or "")
    parts = tuple(int(n) for n in nums[:3])
    return parts + (0,) * (3 - len(parts))


def is_newer(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def repo_homepage() -> str:
    if config.UPDATE_HOMEPAGE:
        return config.UPDATE_HOMEPAGE.rstrip("/")
    if config.UPDATE_REPO:
        return "https://github.com/" + config.UPDATE_REPO
    return ""


def configured() -> bool:
    return bool(re.fullmatch(r"[\w.-]+/[\w.-]+", config.UPDATE_REPO))


# ---------------------------------------------------------------- 版本源
def _api_get(path: str, timeout: int = None) -> dict:
    """请求 GitHub API，返回解析后的 JSON。只访问 config.UPDATE_API。"""
    url = config.UPDATE_API + path
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "Mijia-Web-updater")
    if config.UPDATE_TOKEN:
        req.add_header("Authorization", "Bearer " + config.UPDATE_TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=timeout or config.UPDATE_TIMEOUT_S) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise UpdateError("未找到该仓库的 Release（仓库名不对，或还没有发布过版本）")
        if e.code == 403:
            raise UpdateError("GitHub API 访问受限（可能是速率限制，稍后再试或配置 token）")
        raise UpdateError("GitHub API 返回 HTTP %s" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError("无法连接 GitHub：%s" % e)


def _pick_asset(release: dict, version: str) -> dict:
    """从 release 的资产里挑升级包：优先精确名，其次同前缀 .zip。"""
    assets = [a for a in (release.get("assets") or []) if isinstance(a, dict)]
    want = config.UPDATE_ASSET_PREFIX + version + ".zip"
    for a in assets:
        if (a.get("name") or "").lower() == want.lower():
            return a
    for a in assets:
        name = (a.get("name") or "").lower()
        if (name.startswith(config.UPDATE_ASSET_PREFIX.lower())
                and name.endswith(".zip")):
            return a
    raise UpdateError("这个 Release 里没有升级包（应为 %s）" % want)


def fetch_latest() -> dict:
    """拉取最新正式 release 并结构化；prerelease / draft 跳过。"""
    if not configured():
        raise UpdateError("尚未配置 GitHub 仓库，请在设置 MIHOME_UPDATE_REPO 后再检测")
    data = _api_get("/repos/%s/releases/latest" % config.UPDATE_REPO)
    if data.get("draft") or data.get("prerelease"):
        raise UpdateError("最新版本是预发布，暂不提供升级")
    tag = (data.get("tag_name") or "").strip()
    if not tag:
        raise UpdateError("Release 缺少版本号（tag_name）")
    version = tag[1:] if tag.lower().startswith("v") else tag
    try:
        asset = _pick_asset(data, version)
    except UpdateError:
        asset = None
    return {
        "tag": tag,
        "version": version,
        "name": data.get("name") or tag,
        "body": data.get("body") or "",
        "url": data.get("html_url") or repo_homepage(),
        "published_at": data.get("published_at") or "",
        "asset": None if asset is None else {
            "name": asset.get("name") or "",
            "size": int(asset.get("size") or 0),
            "url": asset.get("browser_download_url") or "",
            "digest": (asset.get("digest") or "").strip(),  # sha256:xxxx
        },
    }


def check() -> dict:
    """检测是否有新版本。失败也返回结构化结果，前端直接展示 error。"""
    base = {
        "configured": configured(),
        "current": config.VERSION,
        "homepage": repo_homepage(),
        "repo": config.UPDATE_REPO,
    }
    if not configured():
        return dict(base, ok=False, error="尚未配置 GitHub 仓库地址，无法检测新版本")
    try:
        rel = fetch_latest()
    except UpdateError as e:
        return dict(base, ok=False, error=str(e))
    return dict(base, ok=True, error="", has_update=is_newer(rel["version"], config.VERSION),
                latest=rel)


# ---------------------------------------------------------------- 下载
def _safe_download(url: str, dest: str, expect_size: int = 0) -> None:
    """从 release 给出的 URL 下载，校验协议/主机、体积上限与可选 digest。"""
    from urllib.parse import urlparse
    p = urlparse(url)
    if p.scheme != "https":
        raise UpdateError("升级包 URL 必须是 https")
    host = (p.hostname or "").lower()
    api_host = (urlparse(config.UPDATE_API).hostname or "").lower()
    if not _download_host_ok(host, api_host):
        raise UpdateError("升级包下载地址不在允许清单内：%s" % host)

    req = urllib.request.Request(url)
    req.add_header("User-Agent", "Mijia-Web-updater")
    if config.UPDATE_TOKEN:
        req.add_header("Authorization", "Bearer " + config.UPDATE_TOKEN)
    tmp = dest + ".part"
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=config.UPDATE_TIMEOUT_S) as r, \
                open(tmp, "wb") as f:
            # GitHub 会把下载 302 到 CDN，跟随重定向后再校验一次最终主机
            final_host = (urlparse(r.geturl()).hostname or "").lower()
            if not _download_host_ok(final_host, api_host):
                raise UpdateError("升级包被重定向到不允许的主机：%s" % final_host)
            declared = r.headers.get("Content-Length")
            cap = config.UPDATE_MAX_BYTES
            if declared and declared.isdigit() and int(declared) > cap:
                raise UpdateError("升级包超过体积上限（%d MB）" % (cap // 1024 // 1024))
            while True:
                chunk = r.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > cap:
                    raise UpdateError("升级包超过体积上限，已中止下载")
                f.write(chunk)
        if expect_size and total != expect_size:
            raise UpdateError("升级包大小不符（期望 %d，实际 %d）" % (expect_size, total))
        os.replace(tmp, dest)
    except urllib.error.HTTPError as e:
        raise UpdateError("下载升级包失败：HTTP %s" % e.code)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise UpdateError("下载升级包失败：%s" % e)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _safe_expect_size(asset: dict) -> int:
    """决定是否用 API 的 size 做精确校验。

    Release 资产被替换（删旧传新）后，GitHub API 的 size 元数据可能短暂滞后，
    精确匹配会误伤合法升级包。资产带 sha256 digest 时以 digest 为权威完整性
    校验，跳过 size 精确匹配；下载体积上限（UPDATE_MAX_BYTES）始终生效。
    """
    digest = (asset.get("digest") or "").strip().lower()
    if digest.startswith("sha256:"):
        return 0
    return int(asset.get("size") or 0)


def _verify_digest(path: str, digest: str) -> None:
    if not digest:
        return
    import hashlib
    algo, _, expect = digest.partition(":")
    if algo.lower() != "sha256" or not expect:
        return
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    if h.hexdigest().lower() != expect.strip().lower():
        raise UpdateError("升级包校验失败（sha256 不匹配），已放弃升级")


# ---------------------------------------------------------------- zip 安全
def _norm(name: str) -> str:
    return name.replace("\\", "/")


def _is_allowed(name: str) -> bool:
    """相对路径是否允许写入。目录项(name 以 / 结尾)也走这里。"""
    n = _norm(name)
    if not n or n.startswith("/") or ":" in n.split("/")[0]:
        return False
    parts = [p for p in n.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return False
    if any(part in DENY_PARTS for part in parts):
        return False
    clean = "/".join(parts)
    if os.path.basename(clean) in DENY_NAMES:
        return False
    return any(clean == pre.rstrip("/") or clean.startswith(pre)
               for pre in ALLOWED_PREFIXES)


def inspect_zip(zip_path: str) -> list:
    """校验升级包结构：只包含白名单普通文件，无 zip-slip、无符号链接。返回文件列表。"""
    files = []
    try:
        with zipfile.ZipFile(zip_path) as z:
            bad = z.testzip()
            if bad:
                raise UpdateError("升级包损坏（CRC 校验失败）：%s" % bad)
            for info in z.infolist():
                name = _norm(info.filename)
                # 符号链接 / 设备文件一律拒绝
                mode = (info.external_attr >> 16) & 0xFFFF
                if stat.S_ISLNK(mode):
                    raise UpdateError("升级包含符号链接，已拒绝：%s" % name)
                if name.endswith("/"):
                    continue
                if not _is_allowed(name):
                    raise UpdateError("升级包含不允许更新的文件：%s" % name)
                files.append("/".join(p for p in name.split("/") if p not in ("", ".")))
    except zipfile.BadZipFile:
        raise UpdateError("升级包不是有效的 zip 文件")
    if not files:
        raise UpdateError("升级包里没有可更新的文件")
    return files


# ---------------------------------------------------------------- 备份/回滚
def _stamp() -> str:
    return time.strftime("%Y%m%d-%H%M%S")


def backup_files(rel_files: list, tag: str = "") -> str:
    """把将被覆盖的现存文件原样备份，返回备份目录名。"""
    name = _stamp() + ("-" + tag if tag else "")
    dst_root = os.path.join(config.UPDATE_BACKUP, name)
    for rel in rel_files:
        src = os.path.join(APP_DIR, rel)
        if not os.path.isfile(src):
            continue
        dst = os.path.join(dst_root, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
    return name


def restore_backup(name: str) -> None:
    """从指定备份还原（用于失败回滚或手动回滚）。"""
    root = os.path.join(config.UPDATE_BACKUP, name)
    if not os.path.isdir(root):
        raise UpdateError("找不到升级前备份：%s" % name)
    for dirpath, _, filenames in os.walk(root):
        for fn in filenames:
            src = os.path.join(dirpath, fn)
            rel = os.path.relpath(src, root).replace(os.sep, "/")
            if not _is_allowed(rel):
                continue
            dst = os.path.join(APP_DIR, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)


def _prune_backups() -> None:
    try:
        names = sorted(n for n in os.listdir(config.UPDATE_BACKUP)
                       if os.path.isdir(os.path.join(config.UPDATE_BACKUP, n)))
    except OSError:
        return
    for old in names[:-config.UPDATE_BACKUP_KEEP]:
        shutil.rmtree(os.path.join(config.UPDATE_BACKUP, old), ignore_errors=True)


def _write_state(data: dict) -> None:
    tmp = config.UPDATE_STATE_PATH + ".part"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, config.UPDATE_STATE_PATH)


def read_state() -> dict:
    try:
        with open(config.UPDATE_STATE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def backups() -> list:
    try:
        return sorted((n for n in os.listdir(config.UPDATE_BACKUP)
                       if os.path.isdir(os.path.join(config.UPDATE_BACKUP, n))),
                      reverse=True)
    except OSError:
        return []


def rollback() -> dict:
    """回滚到最近一次升级前。稳妥起见回滚后仍需重启。"""
    history = backups()
    if not history:
        raise UpdateError("没有可回滚的备份")
    target = history[0]
    try:
        # 先备份当前（可能已升级）状态，避免回滚点丢失
        cur = inspect_and_list()
        backup_files(cur, "pre-rollback")
        restore_backup(target)
    except UpdateError:
        raise
    except OSError as e:
        raise UpdateError("回滚失败：%s" % e)
    _write_state({"rolled_back_to": target, "at": time.time(), "version": config.VERSION})
    return {"ok": True, "backup": target, "restart_required": True}


def inspect_and_list() -> list:
    """列出当前程序目录里所有允许升级的现存文件，用于整包备份。"""
    out = []
    for prefix in ALLOWED_PREFIXES:
        if not prefix.endswith("/"):
            p = os.path.join(APP_DIR, prefix)
            if os.path.isfile(p):
                out.append(prefix)
            continue
        root = os.path.join(APP_DIR, prefix)
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if d not in DENY_PARTS and not d.startswith(".")]
            for fn in filenames:
                if fn in DENY_NAMES:
                    continue
                rel = os.path.relpath(os.path.join(dirpath, fn), APP_DIR).replace(os.sep, "/")
                if _is_allowed(rel):
                    out.append(rel)
    return sorted(set(out))


# ---------------------------------------------------------------- 应用升级
def apply(release: dict = None) -> dict:
    """下载并应用升级。release 省略时自动取 latest；返回是否需要重启。"""
    if release is None:
        release = fetch_latest()
    if not is_newer(release["version"], config.VERSION):
        return {"ok": False, "error": "当前已是最新版本", "noop": True}
    asset = release.get("asset")
    if not asset or not asset.get("url"):
        raise UpdateError("这个 Release 没有可下载的升级包资产")
    os.makedirs(config.UPDATE_DOWNLOAD, exist_ok=True)
    fname = asset.get("name") or ("update-" + release["version"] + ".zip")
    if not fname.endswith(".zip"):
        fname += ".zip"
    dest = os.path.join(config.UPDATE_DOWNLOAD, fname)
    log.info("开始下载升级包 %s", asset["url"])
    _safe_download(asset["url"], dest, _safe_expect_size(asset))
    _verify_digest(dest, asset.get("digest") or "")
    files = inspect_zip(dest)
    # 覆盖前整包备份（不只备份被改文件，回滚更可靠）
    bname = backup_files(inspect_and_list(), "pre-" + release["version"])
    try:
        with zipfile.ZipFile(dest) as z:
            for rel in files:
                target = os.path.join(APP_DIR, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                with z.open(rel.replace("\\", "/")) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
        _prune_backups()
        _write_state({
            "from": config.VERSION, "to": release["version"],
            "tag": release["tag"], "url": release["url"],
            "backup": bname, "at": time.time(),
        })
        log.info("升级已应用：%s -> %s（备份 %s）", config.VERSION,
                 release["version"], bname)
    except Exception as e:
        log.warning("升级写入失败，正在回滚：%s", e)
        try:
            restore_backup(bname)
        except Exception as re:
            log.error("回滚也失败：%s", re)
            raise UpdateError("升级失败且回滚失败：%s；请从备份 %s 手动恢复" % (e, bname))
        raise UpdateError("升级失败，已回滚到升级前：%s" % e)
    return {
        "ok": True,
        "from": config.VERSION,
        "to": release["version"],
        "tag": release["tag"],
        "backup": bname,
        "changed": len(files),
        "restart_required": True,
        "auto_restart": config.UPDATE_AUTO_RESTART,
    }
