/* 登录状态机（Vue 版）。
 *
 * 与旧界面 static/app.js 一一对应：
 *   waitForRestore → bootstrap        startQr / pollQr / stopQrPoll 同名
 *   setQrStatus → setQrStatus          showQrOverlay → showOverlay
 *   btn-login → passwordLogin          btn-otp → submitOtp
 *   btn-logout → logout                onLoginSuccess → onLoginSuccess
 * 唯一差别：登录成功后不自己 setTimeout 收页，而是进 entering 态，
 * 由 LoginPage 调 LoginCat.playIn(700, finishEnter)，让猫先跳完再进门。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import {
  LOGIN_HOP_MS,
  QR_POLL_MS,
  QR_TEXT,
  RESTORE_MAX_TRIES,
  RESTORE_STEP_MS,
  classifyPoll,
  classifyStart,
  moodForStatus,
  restoreDecision,
  statusFor,
  type PollResult,
  type QrClass,
  type StatusResult,
} from '../login/core'
import type { Mood } from '../login/cat'

export type AuthPhase = 'checking' | 'login' | 'entering' | 'app'
export type LoginTab = 'qr' | 'pwd'

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path)
  return (await r.json()) as T
}
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return (await r.json()) as T
}
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export const useAuthStore = defineStore('auth', () => {
  const phase = ref<AuthPhase>('checking')
  const tab = ref<LoginTab>('qr')
  const qrText = ref<string>(QR_TEXT.checking)
  const qrCls = ref<QrClass>('')
  const qrSrc = ref<string>('')
  const overlay = ref<string>('')
  const busy = ref(false)
  const loginMsg = ref('')
  const otpVisible = ref(false)
  const user = ref('')

  const loggedIn = computed(() => phase.value === 'app' || phase.value === 'entering')
  const mood = computed<Mood>(() => moodForStatus(qrText.value, qrCls.value))
  const hopMs = LOGIN_HOP_MS

  let pollTimer: ReturnType<typeof setInterval> | null = null

  function stopQrPoll(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  function setQrStatus(text: string, cls: QrClass = ''): void {
    qrText.value = text
    qrCls.value = cls
  }

  function showOverlay(text: string): void {
    overlay.value = text
  }

  /** 启动时后端可能正在用本机 token 恢复登录，最多等 6 秒 */
  async function waitForRestore(): Promise<boolean> {
    for (let i = 0; i < RESTORE_MAX_TRIES; i++) {
      let r: StatusResult | null = null
      try {
        r = await apiGet<StatusResult>('/api/status')
      } catch {
        // 网络抖动继续等，与旧版一致
      }
      const decision = restoreDecision(r)
      if (decision === 'logged') return true
      if (decision === 'show') return false
      await sleep(RESTORE_STEP_MS)
    }
    return false
  }

  async function bootstrap(): Promise<void> {
    if (await waitForRestore()) {
      phase.value = 'app'
      return
    }
    phase.value = 'login'
  }

  async function startQr(): Promise<void> {
    stopQrPoll()
    setQrStatus(QR_TEXT.fetching, '')
    showOverlay('')
    try {
      const r = await apiPost<{ ok?: boolean; error?: string }>('/api/login/qr/start', {})
      const verdict = classifyStart(r)
      setQrStatus(verdict.text, verdict.cls)
      if (verdict.already) {
        onLoginSuccess()
        return
      }
      if (!verdict.ok) {
        showOverlay(verdict.overlay)
        return
      }
      qrSrc.value = '/api/login/qr/image?t=' + Date.now()
      pollTimer = setInterval(pollQr, QR_POLL_MS)
    } catch {
      setQrStatus(QR_TEXT.network, 'err')
    }
  }

  async function pollQr(): Promise<void> {
    try {
      const r = await apiGet<PollResult>('/api/login/qr/poll')
      const action = classifyPoll(r)
      const s = statusFor(action, r.error)
      setQrStatus(s.text, s.cls)
      if (s.stop) stopQrPoll()
      if (s.overlay) showOverlay(s.overlay)
      if (action === 'ok') onLoginSuccess()
      else if (action === 'restoring') showOverlay('')
    } catch {
      // 短暂网络抖动继续等，不打断轮询
    }
  }

  function setTab(next: LoginTab): void {
    tab.value = next
    if (next === 'qr') void startQr()
    else stopQrPoll()
  }

  function onLoginSuccess(): void {
    stopQrPoll()
    setQrStatus(QR_TEXT.success, 'ok')
    phase.value = 'entering'
  }

  /** 由 LoginCat.playIn 在猫跳完后回调 */
  function finishEnter(): void {
    if (phase.value === 'entering') phase.value = 'app'
  }

  async function passwordLogin(username: string, password: string): Promise<boolean> {
    if (!username.trim() || !password) {
      loginMsg.value = '请填写账号和密码'
      return false
    }
    loginMsg.value = '登录中…'
    busy.value = true
    try {
      const r = await apiPost<{ ok?: boolean; error?: string; user?: string }>(
        '/api/login', { username: username.trim(), password },
      )
      if (r.ok) {
        loginMsg.value = ''
        user.value = r.user || ''
        onLoginSuccess()
        return true
      }
      loginMsg.value = r.error || '登录失败'
      otpVisible.value = true
      return false
    } catch {
      loginMsg.value = '网络异常，稍后重试'
      return false
    } finally {
      busy.value = false
    }
  }

  async function submitOtp(code: string): Promise<boolean> {
    try {
      await apiPost<{ ok?: boolean }>('/api/otp', { code: code.trim() })
      loginMsg.value = '验证码已提交，请稍候再刷新'
      return true
    } catch {
      loginMsg.value = '验证码提交失败'
      return false
    }
  }

  async function logout(): Promise<void> {
    stopQrPoll()
    try {
      await apiPost<{ ok?: boolean }>('/api/logout', {})
    } catch {
      // 后端不可达时也回到登录页，避免卡在已登录界面
    }
    user.value = ''
    loginMsg.value = ''
    otpVisible.value = false
    qrSrc.value = ''
    setQrStatus(QR_TEXT.checking, '')
    // phase 变成 login 会重新挂载 LoginPage，它的 phase 监听负责取码；
    // 这里不要再调一次 startQr，否则同一次退出会发两个 /qr/start 请求。
    phase.value = 'login'
  }

  function destroy(): void {
    stopQrPoll()
  }

  return {
    phase, tab, qrText, qrCls, qrSrc, overlay, busy, loginMsg, otpVisible, user,
    loggedIn, mood, hopMs,
    bootstrap, startQr, pollQr, stopQrPoll, setQrStatus, showOverlay, setTab,
    onLoginSuccess, finishEnter, passwordLogin, submitOtp, logout, destroy,
  }
})
