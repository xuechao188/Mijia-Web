"""事件流：SQLite 落盘，所有操作/状态变化/失败原因都有记录。"""
import sqlite3
import threading
import time
from datetime import datetime

import config
import logx

log = logx.get("mihome.evt")

_lock = threading.RLock()
_db = None


def _conn():
    global _db
    if _db is None:
        config.ensure_dirs()
        _db = sqlite3.connect(config.EVENTS_DB_PATH, check_same_thread=False)
        _db.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            " id INTEGER PRIMARY KEY AUTOINCREMENT,"
            " ts REAL, type TEXT, did TEXT, name TEXT, text TEXT)")
        _db.execute(
            "CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts DESC)")
        _db.commit()
    return _db


def add(evt_type: str, text: str, did: str = "", name: str = ""):
    with _lock:
        try:
            db = _conn()
            db.execute(
                "INSERT INTO events (ts, type, did, name, text) VALUES (?,?,?,?,?)",
                (time.time(), evt_type, str(did), name, text))
            db.commit()
        except sqlite3.Error as e:
            log.warning("事件写入失败: %s", e)


def recent(limit=50):
    with _lock:
        try:
            db = _conn()
            rows = db.execute(
                "SELECT ts, type, did, name, text FROM events"
                " ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
        except sqlite3.Error:
            return []
    out = []
    for ts, typ, did, name, text in rows:
        out.append({
            "ts": ts, "time": datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S"),
            "type": typ, "did": did, "name": name, "text": text,
        })
    return out


def summary():
    """最近 24 小时按类型计数。"""
    since = time.time() - 86400
    with _lock:
        try:
            db = _conn()
            rows = db.execute(
                "SELECT type, COUNT(*) FROM events WHERE ts>=? GROUP BY type",
                (since,)).fetchall()
        except sqlite3.Error:
            return {}
    return {t: n for t, n in rows}
