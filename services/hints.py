"""把云端/网络异常翻译成可操作的中文提示。

原来放在 services/scheduler.py 里，定时规则整体下线后移到此处：
开关、读数、摄像头取流都靠它把「设备离线」「登录失效」讲清楚。
"""
import re


def failure_hint_for(err: Exception) -> str:
    """按错误类型给可操作提示。

    注意：小米错误码有 -704000000 这类九位数，「-7」不能被当成子串匹配，
    否则「云端拒绝 P2P 会话」会被译成「设备离线」，把排查方向带偏。
    """
    text = str(err).lower()
    if "auth" in text or "login" in text or "token" in text:
        return "登录已失效，请在左下角重新登录后再试。"
    if "timeout" in text or "network" in text or "connection" in text:
        return "网络异常或云端超时，稍后自动重试；请检查本机网络。"
    if "offline" in text or "not online" in text or re.search(r"(?<![\d-])-7(?!\d)", text):
        return "设备当前离线，请确认设备通电并在米家 App 中在线后重试。"
    return "执行出错：%s。可手动点击设备开关补执行。" % str(err)[:120]
