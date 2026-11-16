"""异常提示回归：把云端错误翻译成可操作中文（原在 scheduler，定时下线后独立成模块）。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.hints import failure_hint_for  # noqa: E402

ok_n = [0]


def ok(cond, msg):
    if cond:
        ok_n[0] += 1
        print("  ✓", msg)
    else:
        print("  ✗", msg)
        sys.exit(1)


ok("离线" in failure_hint_for(Exception("device offline")), "离线错误给可操作提示")
ok("登录" in failure_hint_for(Exception("login expired")), "登录失效给可操作提示")
ok("网络" in failure_hint_for(Exception("read timeout")), "超时归到网络排查")

# 九位数错误码 -704000000 不能被当成「-7 设备离线」（曾把排查方向带偏）
ok("离线" not in failure_hint_for(Exception("code: -704000000, http 500")),
   "-704000000 不译成设备离线")
ok("离线" in failure_hint_for(Exception("code -7")), "独立的 -7 仍译成设备离线")
ok("执行出错" in failure_hint_for(Exception("weird")), "认不出的错误保留原文并给手动兜底")

print("hints_test: %d 项通过" % ok_n[0])
