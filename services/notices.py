"""设备通知：从米家「消息中心」拉未读消息，本地去重后供界面与浏览器推送。

接口事实（本轮实测，账号内真实返回）：
  POST /app/v2/message/v2/typelist   body={}  →  {"messages": [...]}
    每条：msg_id / type / title / content / did / ctime / is_new
    params.body：event / model / homeRoomExtra{homeName, roomName}
  该接口**只回未读消息**（is_new=1），没有可用的分页参数；同一账号多端
  共享已读态，在手机上点掉就不会再出现。

因此这里绝不回写云端已读状态（免得把手机上的小红点清掉），只在本地按
msg_id 去重：
  · 第一次同步把当时已有的未读当作「历史」（seen=1），不弹不推；
  · 之后新出现的才算新通知（seen=0）；
  · 云端不再列出、且本机仍标未读的，说明在别处读过了，本地跟着标记已读。
"""
import sqlite3
import threading
import time
from datetime import datetime

import config
import logx
from services import cloud
from services.state import S

log = logx.get("mihome.notice")

_lock = threading.RLock()
_db = None
_last_sync = 0.0
_last_error = ""
_thread = None


def _conn():
    global _db
    if _db is None:
        config.ensure_dirs()
        _db = sqlite3.connect(config.NOTICES_DB_PATH, check_same_thread=False)
        _db.execute(
            "CREATE TABLE IF NOT EXISTS notices ("
            " msg_id INTEGER PRIMARY KEY,"
            " ts REAL, kind INTEGER, title TEXT, body TEXT, did TEXT,"
            " model TEXT, home TEXT, room TEXT, event TEXT,"
            " seen INTEGER DEFAULT 0, got REAL)")
        _db.execute("CREATE INDEX IF NOT EXISTS idx_notices_ts ON notices(ts DESC)")
        _db.commit()
    return _db


def _normalize(m: dict) -> dict:
    """云端一条消息 → 本模块的行。字段缺什么都降级，不让界面拿到 None。"""
    params = m.get("params") or {}
    body = params.get("body") or {}
    try:
        msg_id = int(m.get("msg_id") or 0)
    except (TypeError, ValueError):
        msg_id = 0
    ctime = m.get("ctime")
    try:
        ts = float(ctime or 0)
    except (TypeError, ValueError):
        ts = 0.0
    room = body.get("homeRoomExtra") or {}
    return {
        "msg_id": msg_id,
        "ts": ts,
        "kind": int(m.get("type") or 0),
        "title": str(m.get("title") or "").strip(),
        "body": str(m.get("content") or "").strip(),
        "did": str(m.get("did") or body.get("did") or ""),
        "model": str(body.get("model") or ""),
        "home": str(room.get("homeName") or ""),
        "room": str(room.get("roomName") or ""),
        "event": str(body.get("event") or ""),
    }


def _baseline() -> bool:
    """库里还没有任何行 = 第一次同步，把现存未读当历史。"""
    try:
        row = _conn().execute("SELECT COUNT(*) FROM notices").fetchone()
    except sqlite3.Error:
        return False
    return bool(row and int(row[0] or 0) == 0)


def _trim(keep=500):
    try:
        _conn().execute(
            "DELETE FROM notices WHERE msg_id NOT IN"
            " (SELECT msg_id FROM notices ORDER BY ts DESC LIMIT ?)", (int(keep),))
        _conn().commit()
    except sqlite3.Error:
        pass


def sync():
    """拉一轮未读消息。返回本次**新增**的通知列表（已排序，新在前）。

    未登录 / 风控冷却 / 云端暂时不可达都只是跳过，不抛给上层。
    """
    global _last_sync, _last_error
    if not S.get("service") or not S.get("logged_in"):
        return []
    if cloud.cooling() > 0:
        return []
    try:
        res = cloud.call(
            S["service"].miio_request("/v2/message/v2/typelist", {}),
            timeout=15, what="notice")
    except Exception as e:
        _last_error = str(e)[:200]
        log.warning("通知拉取失败: %s", e)
        return []
    msgs = (res or {}).get("messages") if isinstance(res, dict) else None
    if not isinstance(msgs, list):
        _last_error = "返回结构异常"
        return []
    items = [_normalize(m) for m in msgs]
    items = [it for it in items if it["msg_id"]]
    fresh = []
    with _lock:
        db = _conn()
        first = _baseline()
        got = time.time()
        try:
            for it in items:
                exists = db.execute("SELECT 1 FROM notices WHERE msg_id=?",
                                    (it["msg_id"],)).fetchone()
                if exists:
                    continue
                db.execute(
                    "INSERT INTO notices (msg_id, ts, kind, title, body, did, model,"
                    " home, room, event, seen, got) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (it["msg_id"], it["ts"], it["kind"], it["title"], it["body"],
                     it["did"], it["model"], it["home"], it["room"], it["event"],
                     1 if first else 0, got))
                if not first:
                    row = dict(it)
                    row["seen"] = 0
                    fresh.append(row)
            # 云端不再列出、本机还标未读的：在手机上读过了，本地跟着清
            ids = [it["msg_id"] for it in items]
            if len(ids) < 40:
                if ids:
                    marks = ",".join("?" * len(ids))
                    db.execute(
                        "UPDATE notices SET seen=1 WHERE seen=0 AND msg_id NOT IN (%s)"
                        % marks, ids)
                else:
                    db.execute("UPDATE notices SET seen=1 WHERE seen=0")
            db.commit()
        except sqlite3.Error as e:
            log.warning("通知落盘失败: %s", e)
            _last_error = "本地存储异常"
            return []
        _last_sync = got
        _last_error = ""
        _trim()
    fresh.sort(key=lambda r: (r["ts"], r["msg_id"]), reverse=True)
    log.info("通知同步：未读 %d 条，新增 %d 条", len(items), len(fresh))
    return fresh


def _row(r) -> dict:
    msg_id, ts, kind, title, body, did, model, home, room, event, seen = r
    return {
        "msg_id": msg_id, "ts": ts,
        "time": datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") if ts else "",
        "kind": kind, "title": title, "body": body, "did": did, "model": model,
        "home": home, "room": room, "event": event, "seen": int(seen or 0),
    }


def recent(limit=60):
    limit = max(1, min(200, int(limit or 60)))
    with _lock:
        try:
            rows = _conn().execute(
                "SELECT msg_id, ts, kind, title, body, did, model, home, room, event, seen"
                " FROM notices ORDER BY ts DESC, msg_id DESC LIMIT ?", (limit,)).fetchall()
        except sqlite3.Error:
            return []
    return [_row(r) for r in rows]


def unread() -> int:
    with _lock:
        try:
            row = _conn().execute("SELECT COUNT(*) FROM notices WHERE seen=0").fetchone()
        except sqlite3.Error:
            return 0
    return int(row[0] or 0) if row else 0


def mark_read(ids=None):
    """标记已读：ids 为空 = 全部。只动本地，不碰云端。"""
    with _lock:
        db = _conn()
        try:
            if ids:
                clean = [int(i) for i in ids if str(i).isdigit()]
                if clean:
                    db.execute("UPDATE notices SET seen=1 WHERE msg_id IN (%s)"
                               % ",".join("?" * len(clean)), clean)
            else:
                db.execute("UPDATE notices SET seen=1 WHERE seen=0")
            db.commit()
        except (sqlite3.Error, ValueError) as e:
            log.warning("标记已读失败: %s", e)
    return unread()


def snapshot(limit=60):
    return {
        "notices": recent(limit),
        "unread": unread(),
        "last_sync": _last_sync,
        "error": _last_error,
    }


def _loop():
    """常驻轮询：登录态下每 NOTICE_POLL_S 秒拉一次未读。"""
    while True:
        try:
            if S.get("logged_in"):
                sync()
        except Exception as e:      # 后台线程不能死
            log.warning("通知轮询异常: %s", e)
        time.sleep(max(8, int(config.NOTICE_POLL_S)))


def start():
    global _thread
    if _thread and _thread.is_alive():
        return
    _thread = threading.Thread(target=_loop, name="notice-poll", daemon=True)
    _thread.start()
