<script setup lang="ts">
/* 全屏登录页：扫码 / 密码双页签 + 二维码轮询 + 猫四态。
 * 状态与网络请求全部在 stores/auth.ts，这里只负责渲染与编排。 */
import { onBeforeUnmount, ref, watch } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useThemeStore } from '../stores/theme'
import LoginCat from './LoginCat.vue'

const auth = useAuthStore()
const theme = useThemeStore()

const cat = ref<InstanceType<typeof LoginCat> | null>(null)
const username = ref('')
const password = ref('')
const otpCode = ref('')

// 恢复检查结束后才开始取二维码；checking 阶段显示占位提示
watch(
  () => auth.phase,
  (p) => { if (p === 'login' && auth.tab === 'qr') void auth.startQr() },
  { immediate: true },
)

// 登录成功：让猫先跳完再进门，定时器只由猫持有，避免重复收页
watch(
  () => auth.phase,
  (p) => {
    if (p !== 'entering') return
    const done = () => auth.finishEnter()
    if (cat.value) cat.value.playIn(auth.hopMs, done)
    else done()
  },
)

function onLogin(): void {
  void auth.passwordLogin(username.value, password.value)
}
function onOtp(): void {
  void auth.submitOtp(otpCode.value)
}

onBeforeUnmount(() => auth.stopQrPoll())
</script>

<template>
  <div class="login-stage">
    <button class="lp-mode" type="button" :title="theme.mode === 'dark' ? '切换为浅色' : '切换为深色'"
            @click="theme.toggleMode()">
      <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true">
        <circle cx="12" cy="12" r="4"/>
        <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/>
      </svg>{{ theme.mode === 'dark' ? '浅色' : '深色' }}
    </button>

    <div class="lp-shell">
      <div class="lp-cat-side">
        <LoginCat ref="cat" :mood="auth.mood" />
      </div>

      <div class="lp-card">
        <div class="lp-brand">米家Web版</div>
        <div class="lp-sub">登录小米账号，管理你的智能设备</div>

        <div class="lp-tabs" role="tablist" aria-label="登录方式">
          <button class="lp-tab" :class="{ active: auth.tab === 'qr' }" type="button" role="tab"
                  :aria-selected="auth.tab === 'qr'" @click="auth.setTab('qr')">扫码登录</button>
          <button class="lp-tab" :class="{ active: auth.tab === 'pwd' }" type="button" role="tab"
                  :aria-selected="auth.tab === 'pwd'" @click="auth.setTab('pwd')">账号密码</button>
        </div>

        <div v-if="auth.tab === 'qr'" class="lp-qr">
          <div class="qr-frame">
            <img v-if="auth.qrSrc" :src="auth.qrSrc" alt="登录二维码">
            <div v-else class="qr-placeholder">正在检查登录状态…</div>
            <div v-if="auth.overlay" class="qr-overlay">
              <div class="qr-overlay-text">{{ auth.overlay }}</div>
              <button type="button" class="qr-refresh" @click="auth.startQr()">刷新二维码</button>
            </div>
          </div>
          <div class="qr-status" :class="auth.qrCls">{{ auth.qrText }}</div>
          <div class="qr-tip">在米家 App 或小米账号 App 中打开扫一扫</div>
        </div>

        <div v-else class="lp-pwd">
          <input v-model="username" type="text" placeholder="小米账号 / 手机号 / 邮箱"
                 autocomplete="username" :disabled="auth.busy">
          <input v-model="password" type="password" placeholder="密码"
                 autocomplete="current-password" :disabled="auth.busy" @keyup.enter="onLogin">
          <button type="button" class="lp-login-btn" :disabled="auth.busy" @click="onLogin">登 录</button>
          <div class="msg">{{ auth.loginMsg }}</div>
          <div v-if="auth.otpVisible" class="otp-box">
            <input v-model="otpCode" type="text" inputmode="numeric" autocomplete="one-time-code"
                   :placeholder="'输入' + auth.otpMethod + '收到的验证码'" @keyup.enter="onOtp">
            <button type="button" @click="onOtp">提交验证码</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
