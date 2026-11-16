"""
集中配置：所有路径/端口常量。换机器换目录不用改源码。

数据目录外置（参考项目未实现项 #5 的补齐）：
  优先取环境变量 MIHOME_DATA_DIR；否则用平台惯例的用户数据目录。
  程序目录可以是只读的（绿色版/解压即用），缓存与日志照样能写。

注意：一律用 config.XXX 属性访问，不要 `from config import XXX_PATH`。
"""
import os
import sys

APP_NAME = "Mijia-Web"          # 仓库目录名 / 数据目录名
APP_NAME_CN = "米家Web版"       # 界面与文档展示名
VERSION = "0.1.0"

PORT = int(os.environ.get("MIHOME_PORT", "8765"))
# 默认只绑回环：本机使用不需要任何额外防护。
# 部署到虚拟主机时用 MIHOME_HOST=0.0.0.0，并务必同时设置访问密码与域名白名单，
# 或者只让反向代理（127.0.0.1:8765）对外，不要直接把 8765 暴露到公网。
HOST = os.environ.get("MIHOME_HOST", "127.0.0.1")

# 同源守卫允许的主机名。本机三项恒定可用；域名部署时追加域名，
# 例如 MIHOME_ALLOWED_ORIGINS=mihome.example.com,www.example.com。
# 只放主机名不放协议：反向代理终止 TLS 后浏览器看到的是 https，
# 后端看到的却可能是 http，按主机名比对才不会误杀。
LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1")


def allowed_origins() -> tuple:
    extra = [h.strip().lower() for h in
             os.environ.get("MIHOME_ALLOWED_ORIGINS", "").split(",") if h.strip()]
    return LOCAL_HOSTS + tuple(dict.fromkeys(extra))


# 可选 HTTP Basic 访问密码。两项都设置才启用；本机使用留空即可无感。
# 公网部署强烈建议设置：否则任何能访问到端口的人都能操控米家设备。
ACCESS_USER = os.environ.get("MIHOME_ACCESS_USER", "")
ACCESS_PASSWORD = os.environ.get("MIHOME_ACCESS_PASSWORD", "")

# 服务器部署时跳过自动打开浏览器（run.py 用）
NO_BROWSER = os.environ.get("MIHOME_NO_BROWSER", "").strip() in ("1", "true", "yes")

# ---------------------------------------------------------------- 在线升级
# GitHub 仓库，格式 owner/repo。留空则「检测新版本」提示尚未配置，不影响其它功能。
# 发布自己的版本后填这一项即可；版本源固定走 GitHub Releases 的 latest。
UPDATE_REPO = os.environ.get("MIHOME_UPDATE_REPO", "xuechao188/Mijia-Web").strip().strip("/")
# GitHub API 地址（自建 GitHub Enterprise 时改这里）；公网官方版保持默认。
UPDATE_API = os.environ.get("MIHOME_UPDATE_API", "https://api.github.com").strip().rstrip("/")
# 可选个人 token：只为抬高 API 速率限制 / 读私有仓库，留空也能读公开 release。
UPDATE_TOKEN = os.environ.get("MIHOME_UPDATE_TOKEN", "").strip()
# 仓库主页（关于弹窗里展示、可点开）。留空时按 UPDATE_REPO 拼 https://github.com/owner/repo。
UPDATE_HOMEPAGE = os.environ.get("MIHOME_GITHUB_URL", "").strip()
# 升级包资产名前缀：发布时资产命名 <前缀><版本号>.zip，如 Mijia-Web-0.2.0.zip。
UPDATE_ASSET_PREFIX = "Mijia-Web-"
# 下载/解压超时与体积上限（防磁盘打满、防挂死）。
UPDATE_TIMEOUT_S = 30
UPDATE_MAX_BYTES = 200 * 1024 * 1024
# 升级前备份保留份数（放在数据目录 updates/ 下，可手动回滚）。
UPDATE_BACKUP_KEEP = 3
# apply 完成后是否自动重启进程加载新代码。默认开；关掉则需手动重启。
UPDATE_AUTO_RESTART = os.environ.get(
    "MIHOME_UPDATE_AUTO_RESTART", "").strip().lower() not in ("0", "false", "no")

# ---------------------------------------------------------------- 前端版本
# vue    = Vue 3 新界面（static/vue/index.html），默认入口，已全量迁移
# legacy = 原生 JS 旧界面（static/index.html），仅在显式 MIJIA_UI=legacy 时应急回退
# 默认走新版：去掉变量即新版；临时排查可用 MIJIA_UI=legacy python run.py 回退。
# 若新版构建产物不存在会自动回退到 legacy，不会白屏。
UI_FLAVOR = "legacy" if os.environ.get("MIJIA_UI", "").strip().lower() == "legacy" else "vue"

# ---------------------------------------------------------------- 数据目录
def _default_data_dir() -> str:
    override = os.environ.get("MIHOME_DATA_DIR")
    if override:
        return os.path.abspath(override)
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/" + APP_NAME)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, APP_NAME)
    return os.path.expanduser("~/.local/share/" + APP_NAME)


DATA_DIR = _default_data_dir()

# 运行期数据（缓存/事件库/token/分组），全部在数据目录下
TOKEN_PATH = os.path.join(DATA_DIR, "mi.token")
SPEC_CACHE_PATH = os.path.join(DATA_DIR, "spec_cache.json")
DEV_CACHE_PATH = os.path.join(DATA_DIR, "devices_cache.json")
GROUPS_PATH = os.path.join(DATA_DIR, "groups.json")
LAYOUT_PATH = os.path.join(DATA_DIR, "layout.json")
EVENTS_DB_PATH = os.path.join(DATA_DIR, "events.db")
HISTORY_DB_PATH = os.path.join(DATA_DIR, "history.db")
NOTICES_DB_PATH = os.path.join(DATA_DIR, "notices.db")
IR_KEYS_PATH = os.path.join(DATA_DIR, "ir_keys.json")
LOG_DIR = os.path.join(DATA_DIR, "logs")
DEVICE_ID_PATH = os.path.join(DATA_DIR, "device_id")
# 在线升级：下载缓存、升级前备份、升级标记都落在数据目录，不写程序目录
UPDATE_DIR = os.path.join(DATA_DIR, "updates")
UPDATE_DOWNLOAD = os.path.join(UPDATE_DIR, "download")
UPDATE_BACKUP = os.path.join(UPDATE_DIR, "backup")
UPDATE_STATE_PATH = os.path.join(UPDATE_DIR, "state.json")


def device_id() -> str:
    """稳定设备指纹：只生成一次并持久化。

    miservice 默认每次进程启动随机生成 deviceId，频繁变化的设备指纹
    会被小米风控盯上（-127 client withdraw 的一大诱因）。
    """
    try:
        with open(DEVICE_ID_PATH, "r", encoding="utf-8") as f:
            did = f.read().strip()
            if did:
                return did
    except OSError:
        pass
    import secrets
    did = secrets.token_hex(8).upper()
    try:
        with open(DEVICE_ID_PATH, "w", encoding="utf-8") as f:
            f.write(did)
        os.chmod(DEVICE_ID_PATH, 0o600)
    except OSError:
        pass
    return did

# 缓存结构变更时 +1，旧缓存自动作废（v4: switches 多键逐路映射）
CACHE_VERSION = 4

# ---------------------------------------------------------------- 行为参数
# 快轮询（只读开关）间隔：3 秒（参考项目未实现项 #6：4s → 3s）
QUICK_POLL_S = 3
# 全量读数轮询间隔
FULL_POLL_S = 45
# 设备通知（米家消息中心未读）轮询间隔：一次请求，太密会撞风控
NOTICE_POLL_S = 15
# 红外遥控按键表：云端按设备保存，几乎不变，缓存 6 小时再拉一次
IR_KEYS_TTL_S = 6 * 3600
# 按键表预取的并发与间隔（8 台设备串行拉，避免启机瞬间撞 -127）
IR_PREFETCH_GAP_S = 0.35
# 历史曲线：同一 (did,key) 最短采样间隔、保留天数、单次查询最多点数
HISTORY_SAMPLE_S = 300
HISTORY_KEEP_DAYS = 7
HISTORY_MAX_POINTS = 96

# 轮询/云端调用超时
CLOUD_TIMEOUT_S = 30
CONTROL_TIMEOUT_S = 15

# 天气（Open-Meteo 免费接口，无需 key）
WEATHER_CITY = os.environ.get("MIHOME_CITY", "合肥")
WEATHER_TIMEOUT_S = 8
WEATHER_CACHE_S = 600       # 成功数据缓存 10 分钟，避免重复打外部接口
WEATHER_FAIL_CACHE_S = 60   # 失败只短暂负缓存，偶发抖动别让用户干等 10 分钟


def ensure_dirs() -> None:
    """启动时把数据目录建好（幂等）。"""
    for p in (DATA_DIR, LOG_DIR, UPDATE_DIR, UPDATE_DOWNLOAD, UPDATE_BACKUP):
        try:
            os.makedirs(p, exist_ok=True)
        except OSError:
            pass
