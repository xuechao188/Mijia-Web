"""进程级共享状态（登录态、设备视图缓存）。"""
import threading

S = {
    "account": None,     # miservice.MiAccount
    "service": None,     # miservice.MiIOService
    "logged_in": False,
    "restoring": False,  # 启动时正在用本机 token 恢复登录
    "user": "",
    "devices": [],       # 云端原始设备列表
    "views": {},         # did -> 设备视图（build_device_view 输出）
    "live": {},          # did -> 实时属性
    "last_refresh": 0.0,
}

_LOGIN_LOCK = threading.RLock()
_OTP_CODE = {"value": None, "event": threading.Event()}
