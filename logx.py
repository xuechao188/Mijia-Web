"""统一日志出口：logs/Mijia-Web.log，按天轮转留 7 天。"""
import logging
import logging.handlers
import os

import config

_logger = None


def get(name: str = "mihome") -> logging.Logger:
    global _logger
    if _logger is not None and name == "mihome":
        return _logger
    lg = logging.getLogger(name)
    if lg.handlers:
        return lg
    lg.setLevel(os.environ.get("MIHOME_LOG_LEVEL", "INFO").upper())
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s", "%H:%M:%S")
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    lg.addHandler(sh)
    try:
        config.ensure_dirs()
        fh = logging.handlers.TimedRotatingFileHandler(
            os.path.join(config.LOG_DIR, "Mijia-Web.log"),
            when="midnight", backupCount=7, encoding="utf-8")
        fh.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s"))
        lg.addHandler(fh)
    except OSError:
        pass
    if name == "mihome":
        _logger = lg
    return lg
