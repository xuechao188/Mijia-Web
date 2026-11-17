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
  const otpMethod = ref('')          // Phone / Email，提示用户去哪找验证码
  const user = ref('')

  const loggedIn = computed(() => phase.value === 'app' || phase.value === 'entering')
  const mood = computed<Mood>(() => moodForStatus(qrText.value, qrCls.value))
  const hopMs = LOGIN_HOP_MS

  let pollTimer: ReturnType<typeof setInterval> | null = null
  let pwdPollTimer: ReturnType<typeof setInterval> | null = null

  function stopQrPoll(): void {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  /** 密码登录的登录态轮询：验证码提交后 miservice 会自动完成登录，前端据此进主界面 */
  function stopPwdPoll(): void {
    if (pwdPollTimer) {
      clearInterval(pwdPollTimer)
      pwdPollTimer = null
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

  function hasSucceeded(): boolean {
    return phase.value === 'entering' || phase.value === 'app'
  }

  /** 登录成功后收尾：只认第一次，避免轮询与 /api/login 返回同时触发两次。 */
  function succeedOnce(userName?: string): void {
    if (hasSucceeded()) return
    stopPwdPoll()
    busy.value = false
    otpVisible.value = false
    loginMsg.value = ''
    if (userName) user.value = userName
    onLoginSuccess()
  }

  /** 轮询 /api/status：登录成功后进主界面；需要 2FA 时弹验证码输入框。 */
  async function pollPasswordStatus(): Promise<void> {
    try {
      const st = await apiGet<StatusResult>('/api/status')
      if (st.logged_in) {
        succeedOnce()
        return
      }
      // 后端 miservice 已发短信/邮件并挂起等待验证码 —— 立刻给出输入框，
      // 不再等 /api/login 的失败返回（2FA 时它会一直阻塞到登录结束）。
      if (st.otp_needed && !otpVisible.value && !hasSucceeded()) {
        otpVisible.value = true
        otpMethod.value = st.otp_method === 'Email' ? '邮箱' : '手机'
        loginMsg.value = '请输入' + otpMethod.value + '收到的验证码，验证后将自动登录'
      }
    } catch {
      // 短暂网络抖动，继续轮询
    }
  }

  async function passwordLogin(username: string, password: string): Promise<boolean> {
    if (!username.trim() || !password) {
      loginMsg.value = '请填写账号和密码'
      return false
    }
    stopPwdPoll()
    loginMsg.value = '正在登录…'
    busy.value = true
    otpVisible.value = false
    otpMethod.value = ''
    // /api/login 在 2FA 场景会一直阻塞到登录完成（miservice 等验证码），
    // 所以不能用它的返回来判断"要不要验证码"。改为发请求后就轮询 status：
    // 后端一说 otp_needed 就弹输入框；登录完成（含提交验证码后自动完成）就进主界面。
    void apiPost<{ ok?: boolean; error?: string; user?: string }>(
      '/api/login', { username: username.trim(), password },
    ).then((r) => {
      if (r.ok) {
        succeedOnce(r.user)
      } else if (!hasSucceeded()) {
        // 请求返回失败且尚未登录成功：密码错 / 风控等非 2FA 原因。
        stopPwdPoll()
        busy.value = false
        otpVisible.value = false
        loginMsg.value = r.error || '登录失败'
      }
    }).catch(() => {
      if (hasSucceeded()) return
      stopPwdPoll()
      busy.value = false
      otpVisible.value = false
      loginMsg.value = '网络异常，稍后重试'
    })
    pwdPollTimer = setInterval(() => { void pollPasswordStatus() }, 1200)
    return true
  }

  async function submitOtp(code: string): Promise<boolean> {
    if (!code.trim()) {
      loginMsg.value = '请输入验证码'
      return false
    }
    try {
      const r = await apiPost<{ ok?: boolean; error?: string }>('/api/otp', { code: code.trim() })
      if (r.ok === false) {
        loginMsg.value = r.error || '验证码提交失败'
        return false
      }
      // 提交成功后 miservice 会用验证码继续完成登录；轮询 status 检测到 logged_in 自动进主界面。
      otpVisible.value = false
      loginMsg.value = '验证码已提交，正在登录…'
      void pollPasswordStatus()
      return true
    } catch {
      loginMsg.value = '验证码提交失败，请重试'
      return false
    }
  }

  async function logout(): Promise<void> {
    stopQrPoll()
    stopPwdPoll()
    try {
      await apiPost<{ ok?: boolean }>('/api/logout', {})
    } catch {
      // 后端不可达时也回到登录页，避免卡在已登录界面
    }
    user.value = ''
    loginMsg.value = ''
    otpVisible.value = false
    otpMethod.value = ''
    busy.value = false
    qrSrc.value = ''
    setQrStatus(QR_TEXT.checking, '')
    // phase 变成 login 会重新挂载 LoginPage，它的 phase 监听负责取码；
    // 这里不要再调一次 startQr，否则同一次退出会发两个 /qr/start 请求。
    phase.value = 'login'
  }

  function destroy(): void {
    stopQrPoll()
    stopPwdPoll()
  }

  return {
    phase, tab, qrText, qrCls, qrSrc, overlay, busy, loginMsg, otpVisible, otpMethod, user,
    loggedIn, mood, hopMs,
    bootstrap, startQr, pollQr, stopQrPoll, setQrStatus, showOverlay, setTab,
    onLoginSuccess, finishEnter, passwordLogin, submitOtp, logout, destroy,
  }
})
