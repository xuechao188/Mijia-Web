/* Vue 版登录状态机的纯逻辑层。
 *
 * 与旧界面 static/app.js 的下列函数同判据、同文案：
 *   startQr / pollQr / setQrStatus / showQrOverlay / waitForRestore / onLoginSuccess
 * 这里不含 fetch、不含定时器、不碰 DOM；副作用统一放在 stores/auth.ts。
 */

import { moodOf, type Mood } from './cat'

export const QR_POLL_MS = 2500
export const RESTORE_STEP_MS = 500
export const RESTORE_MAX_TRIES = 12     // 12 × 500ms = 6 秒
export const LOGIN_HOP_MS = 700         // 登录成功：猫先跳一下再收页

export type QrClass = '' | 'ok' | 'err'
export type PollAction = 'ok' | 'restoring' | 'expired' | 'error' | 'waiting' | 'idle'
export type RestoreDecision = 'logged' | 'wait' | 'show'

export interface PollResult {
  status?: string
  error?: string
  logged_in?: boolean
  restoring?: boolean
}
export interface StatusResult {
  logged_in?: boolean
  restoring?: boolean
  user?: string
  devices?: number
}
export interface QrStatus { text: string; cls: QrClass }

/** 与旧 app.js 逐字一致的二维码状态文案 */
export const QR_TEXT = {
  fetching: '正在获取二维码…',
  waiting: '请使用米家 App 扫码',
  success: '登录成功，正在进入…',
  restoring: '正在恢复登录（等待小米风控解除）…',
  expired: '二维码已过期',
  error: '扫码登录出错',
  startFailed: '二维码获取失败',
  network: '网络异常，稍后重试',
  checking: '正在检查登录状态…',
} as const

/** /api/login/qr/poll 的一次返回 → 应该走哪条分支 */
export function classifyPoll(r: PollResult | null | undefined): PollAction {
  if (!r) return 'idle'
  if (r.status === 'ok' || r.logged_in) return 'ok'
  if (r.restoring) return 'restoring'
  if (r.status === 'expired') return 'expired'
  if (r.status === 'error') return 'error'
  if (r.status === 'waiting') return 'waiting'
  return 'idle'
}

/** 轮询分支 → 状态条文案 / 心情类 / 是否停轮询 / 遮罩文案 */
export function statusFor(
  action: PollAction, error?: string,
): QrStatus & { stop: boolean; overlay: string } {
  switch (action) {
    case 'ok':
      return { text: QR_TEXT.success, cls: 'ok', stop: true, overlay: '' }
    case 'restoring':
      return { text: QR_TEXT.restoring, cls: '', stop: false, overlay: '' }
    case 'expired':
      return { text: QR_TEXT.expired, cls: 'err', stop: true, overlay: QR_TEXT.expired }
    case 'error':
      return { text: error || QR_TEXT.error, cls: 'err', stop: true, overlay: '出错了' }
    case 'waiting':
      return { text: QR_TEXT.waiting, cls: '', stop: false, overlay: '' }
    default:
      return { text: QR_TEXT.waiting, cls: '', stop: false, overlay: '' }
  }
}

/** 启动本机 token 恢复检查：已登录 → 进主界面；明确没在恢复 → 立刻显示登录页 */
export function restoreDecision(r: StatusResult | null | undefined): RestoreDecision {
  if (!r) return 'wait'
  if (r.logged_in) return 'logged'
  if (!r.restoring) return 'show'
  return 'wait'
}

/** 二维码 /api/login/qr/start 的返回：成功、已登录、失败 */
export function classifyStart(r: { ok?: boolean; error?: string } | null | undefined):
  { ok: boolean; already: boolean; text: string; cls: QrClass; overlay: string } {
  if (r && r.ok) return { ok: true, already: false, text: QR_TEXT.waiting, cls: '', overlay: '' }
  const err = (r && r.error) || ''
  if (err.indexOf('已登录') >= 0) {
    return { ok: false, already: true, text: QR_TEXT.success, cls: 'ok', overlay: '' }
  }
  return { ok: false, already: false, text: err || QR_TEXT.startFailed, cls: 'err', overlay: '获取失败' }
}

/** 状态条文案 → 猫的心情（与旧 setQrStatus 里 LoginCat.moodOf 一致） */
export function moodForStatus(text: string, cls: QrClass = ''): Mood {
  return moodOf(text, cls)
}
