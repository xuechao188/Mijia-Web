"""API 层回归：同源守卫、quick 多键合并、定时时间校验、场景参数校验。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tmp = tempfile.mkdtemp(prefix="mijia-test-")
os.environ["MIHOME_DATA_DIR"] = tmp

import app as appmod  # noqa: E402
from routes import auth as authmod  # noqa: E402
from services import live as livemod  # noqa: E402
from services.state import S  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


# 登录打桩：守卫测试只关心是否被 403 拦截，不真连小米云端
authmod.dev.login = lambda u, p: False

fa = appmod.create_app()
fa.config["TESTING"] = True
c = fa.test_client()

# ---- 同源守卫（修 bug：原 host-in-origin 判断对 rebinding 失效）----
# 恶意 Origin：Host 与 Origin 同为恶意域名（DNS rebinding 场景）→ 必须拦截
r = c.post("/api/login", json={"username": "x", "password": "y"},
           headers={"Origin": "http://evil.example", "Host": "evil.example"})
ok(r.status_code == 403, "同源守卫：恶意 Origin（rebinding 场景）被拦截")
# 本机 Origin 放行（登录参数校验会先返回 400，但不是 403）
r = c.post("/api/login", json={"username": "x", "password": "y"},
           headers={"Origin": "http://127.0.0.1:8765"})
ok(r.status_code != 403, "同源守卫：本机 Origin 放行")
# 无 Origin/Referer（本机 CLI）放行
r = c.post("/api/login", json={"username": "x", "password": "y"})
ok(r.status_code != 403, "同源守卫：无 Origin（CLI）放行")
# 恶意 Referer 同样拦截
r = c.post("/api/login", json={"username": "x", "password": "y"},
           headers={"Referer": "http://bad.example/page"})
ok(r.status_code == 403, "同源守卫：恶意 Referer 被拦截")

# ---- quick 轮询合并多键开关各路状态（修 bug：原来只合并 on）----
S["views"] = {"d1": {"did": "d1", "name": "双键", "switches": [
    {"key": "on1", "label": "左", "siid": 2, "piid": 1},
    {"key": "on2", "label": "右", "siid": 3, "piid": 1}]}}
S["live"] = {"d1": {"on1": False, "on2": False, "brightness": 50}}


def fake_read(views, quick=False):
    return {"d1": {"on1": True, "on2": True, "on": True}}


livemod.read_live = fake_read
r = c.get("/api/live?quick=1")
data = r.get_json()
ok(data["ok"], "quick 轮询返回成功")
ok(data["live"]["d1"]["on1"] is True and
   data["live"]["d1"]["on2"] is True, "quick 合并保留多键各路状态（on1/on2）")
ok(data["live"]["d1"].get("brightness") == 50, "quick 不清其他读数")

# ---- 场景参数校验（修 bug：缺 scene_id 原来会走到云端才挂）----
r = c.post("/api/scenes/run", json={})
ok(r.status_code == 400, "缺 scene_id 返回 400")

# ---- 开关分路文案：云端英文 label 不能原样进事件流 ----
from routes.devices import _switch_text  # noqa: E402

ok(_switch_text("Left Switch Service") == "左键", "Left Switch Service → 左键")
ok(_switch_text("Right Switch Service") == "右键", "Right Switch Service → 右键")
ok(_switch_text("Middle Switch Service") == "中键", "Middle Switch Service → 中键")
ok(_switch_text("switch-toggle") == "切换", "switch-toggle → 切换")
ok(_switch_text("Switch Service") == "按键", "无法区分的 switch → 按键")
ok(_switch_text("左键") == "左键" and _switch_text("") == "", "中文原样、空值不拼")

print("api_test: %d 项通过" % ok_n[0])
