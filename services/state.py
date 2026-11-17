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
# OTP 二次验证的共享状态：
#   value/event —— 前端提交的验证码与唤醒信号
#   needed      —— 后端正在等待验证码（miservice 已发短信/邮件，_otp_waiter 挂起）
#   method      —— 验证方式（Phone/Email），供前端提示"手机/邮箱收到的验证码"
# 前端通过 /api/status 轮询 needed，从"登录失败才显示输入框"改为"后端一说要验证码就显示"。
_OTP_CODE = {"value": None, "event": threading.Event(), "needed": False, "method": ""}
