"""数值读数历史：SQLite 采样落盘，供卡片/抽屉画趋势曲线。

数据来源是实时轮询的 sensor 读数，不额外发云端请求。
同一个 (did, key) 默认每 5 分钟最多一个点，保留 7 天；
查询时按时间桶等分降采样，避免一次返回几万行。

部分运行环境（沙箱/只读数据目录）允许写 JSON 但不允许 SQLite 建表，
此时自动回退到临时目录，保证曲线功能不整体失效；
回退目录里的数据会随系统清理而丢失，属降级行为。
"""
import math
import os
import sqlite3
import tempfile
import threading
import time

import config
import logx

log = logx.get("mihome.history")

_lock = threading.RLock()
_db = None
_db_path = ""
_last = {}            # (did, key) -> 上次写入时间（进程内节流）
_last_cleanup = 0.0

# 只记传感器读数；开关、模式、目标温度这类设定值画曲线没有意义
RECORD_KEYS = frozenset({
    "temperature", "humidity", "battery_level", "illumination",
    "power", "voltage", "current", "filter_life", "pressure",
    "pm2.5-density", "co2-density", "water-level", "motion",
    "contact",
})

_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS metrics ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " ts REAL NOT NULL, did TEXT NOT NULL, key TEXT NOT NULL,"
    " value REAL NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_metrics_lookup ON metrics(did, key, ts)",
    "CREATE INDEX IF NOT EXISTS idx_metrics_ts ON metrics(ts)",
)


def _candidates():
    """首选数据目录；不可写时退到系统临时目录（沙箱环境实测需要）。"""
    paths = [config.HISTORY_DB_PATH,
             os.path.join(tempfile.gettempdir(), "Mijia-Web-history.db")]
    out = []
    for p in paths:
        if p not in out:
            out.append(p)
    return out


def _conn():
    """返回可用连接；全部候选都失败时返回 None（调用方降级，不抛给 Flask）。

    关键：只有建表/索引全部成功后才把连接缓存到全局，避免把
    「建表失败的半截连接」留下来，后续一直报 no such table。
    """
    global _db, _db_path
    if _db is not None:
        return _db
    config.ensure_dirs()
    for path in _candidates():
        db = None
        try:
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            db = sqlite3.connect(path, check_same_thread=False)
            for sql in _SCHEMA:
                db.execute(sql)
            db.commit()
            _db, _db_path = db, path
            if path != config.HISTORY_DB_PATH:
                log.warning("数据目录不可写，历史库回退到 %s（重启机器后数据清空）", path)
            return _db
        except (sqlite3.Error, OSError) as e:
            if db is not None:
                try:
                    db.close()
                except sqlite3.Error:
                    pass
            log.warning("历史库 %s 不可用: %s", path, e)
    return None


def _cleanup(db, now):
    global _last_cleanup
    if now - _last_cleanup < 3600:
        return
    cutoff = now - config.HISTORY_KEEP_DAYS * 86400
    try:
        db.execute("DELETE FROM metrics WHERE ts < ?", (cutoff,))
        db.commit()
    except sqlite3.Error as e:
        log.warning("历史清理失败: %s", e)
    _last_cleanup = now


def record(live: dict, now=None, interval=None):
    """把一轮实时读数写入历史。返回本次写入的点数。"""
    now = now if now is not None else time.time()
    interval = config.HISTORY_SAMPLE_S if interval is None else interval
    rows, stamps = [], []
    with _lock:
        for did, values in (live or {}).items():
            if not isinstance(values, dict):
                continue
            for key, val in values.items():
                if key not in RECORD_KEYS or isinstance(val, bool):
                    continue
                if not isinstance(val, (int, float)):
                    continue
                f = float(val)
                if not math.isfinite(f):
                    continue
                k = (str(did), str(key))
                if now - _last.get(k, 0) < interval:
                    continue
                # 先不更新 _last：写库失败时不能把这次采样算掉
                stamps.append(k)
                rows.append((now, k[0], k[1], f))
        if not rows:
            return 0
        db = _conn()
        if db is None:
            return 0
        try:
            db.executemany(
                "INSERT INTO metrics (ts, did, key, value) VALUES (?,?,?,?)",
                rows)
            db.commit()
            for k in stamps:
                _last[k] = now
            _cleanup(db, now)
        except sqlite3.Error as e:
            log.warning("历史写入失败: %s", e)
            return 0
    return len(rows)


def _downsample(points, max_points):
    """按时间等分桶取均值；不足 max_points 时原样返回。"""
    if len(points) <= max_points:
        return points
    t0, t1 = points[0][0], points[-1][0]
    span = max(1e-9, t1 - t0)
    buckets = [[] for _ in range(max_points)]
    for ts, val in points:
        i = min(max_points - 1, int((ts - t0) / span * max_points))
        buckets[i].append((ts, val))
    out = []
    for b in buckets:
        if not b:
            continue
        out.append([sum(t for t, _ in b) / len(b),
                    round(sum(v for _, v in b) / len(b), 3)])
    return out


def query(did=None, hours=24, max_points=None, now=None, keys=None):
    """返回 {did: {key: [[ts, value], ...]}}；按时间正序。"""
    hours = max(0.1, min(168.0, float(hours or 24)))
    max_points = max(2, min(500, int(max_points or config.HISTORY_MAX_POINTS)))
    now = now if now is not None else time.time()
    since = now - hours * 3600
    sql = "SELECT ts, did, key, value FROM metrics WHERE ts >= ?"
    args = [since]
    if did:
        sql += " AND did = ?"
        args.append(str(did))
    if keys:
        wanted = [str(k) for k in keys]
        sql += " AND key IN (%s)" % ",".join("?" * len(wanted))
        args.extend(wanted)
    sql += " ORDER BY ts ASC"
    with _lock:
        db = _conn()
        if db is None:
            return {}
        try:
            rows = db.execute(sql, args).fetchall()
        except sqlite3.Error as e:
            log.warning("历史查询失败: %s", e)
            return {}
    grouped = {}
    for ts, d, k, v in rows:
        grouped.setdefault(d, {}).setdefault(k, []).append([ts, v])
    return {d: {k: _downsample(pts, max_points) for k, pts in ks.items()}
            for d, ks in grouped.items()}


def count(now=None):
    """统计保留的点数（诊断/测试用）。"""
    now = now if now is not None else time.time()
    cutoff = now - config.HISTORY_KEEP_DAYS * 86400
    with _lock:
        db = _conn()
        if db is None:
            return 0
        try:
            return db.execute(
                "SELECT COUNT(*) FROM metrics WHERE ts >= ?", (cutoff,)).fetchone()[0]
        except sqlite3.Error:
            return 0
