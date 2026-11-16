"""事件流与天气接口。"""
from flask import Blueprint, jsonify, request

import logx
from services import evtlog
from services import weather

log = logx.get("mihome.misc.api")
bp = Blueprint("misc", __name__)


@bp.route("/api/events")
def events():
    limit = 50
    return jsonify({"ok": True, "events": evtlog.recent(limit),
                    "summary": evtlog.summary()})


@bp.route("/api/weather")
def get_weather():
    city = (request.args.get("city") or "").strip()
    w = weather.fetch(city or None)
    return jsonify({"ok": w is not None, "weather": w})
