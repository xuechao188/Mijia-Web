/* 设备通知数据层：拉本地 /api/notices、右下角卡片提醒、浏览器系统通知。
 *
 * 分工：
 *   · 后端每 15 秒轮询米家消息中心的未读消息，按 msg_id 去重后落盘；
 *   · 前端只轮这个本机接口（10 秒），拿到「未读 + 新出现的」再决定要不要提醒；
 *   · 已提示过的 msg_id 记在内存里，同样的消息不重复弹、不重复推系统通知。
 *
 * 第一次加载只建基线：页面上已有的未读不再弹一遍（后端首次同步也已把它们
 * 当历史），避免刚打开就糊一脸卡片。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { isFresh, noticeLine, noticeTitle } from '../panels/notices'
import type { NoticeItem } from '../panels/types'
import { useDevicesStore } from './devices'

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

export const NOTICE_POLL_MS = 10000
export const NOTICE_TOAST_MS = 9000
export const NOTICE_TOAST_MAX = 3

type NoticesResp = {
  ok: boolean
  notices?: NoticeItem[]
  unread?: number
  last_sync?: number
  error?: string
  new?: number
}

export type NoticePerm = NotificationPermission | 'unsupported'

export const useNoticesStore = defineStore('notices', () => {
  const devices = useDevicesStore()

  const list = ref<NoticeItem[]>([])
  const unread = ref(0)
  const lastSync = ref(0)
  const err = ref('')
  const loading = ref(false)
  /* 右下角正在展示的卡片；最多 3 张，新的压在上面 */
  const toasts = ref<NoticeItem[]>([])
  const perm = ref<NoticePerm>(
    typeof window !== 'undefined' && 'Notification' in window
      ? Notification.permission
      : 'unsupported',
  )

  const hasUnread = computed(() => unread.value > 0)
  const badge = computed(() => (unread.value > 99 ? '99+' : String(unread.value)))

  /* 已提示过的消息：不进响应式，只做去重 */
  const known = new Set<number>()
  let bootstrapped = false
  let timer: ReturnType<typeof setInterval> | null = null
  const dismissTimers = new Map<number, ReturnType<typeof setTimeout>>()

  function dismiss(msgId: number): void {
    const t = dismissTimers.get(msgId)
    if (t) clearTimeout(t)
    dismissTimers.delete(msgId)
    toasts.value = toasts.value.filter((n) => n.msg_id !== msgId)
  }

  function pushToast(n: NoticeItem): void {
    if (toasts.value.some((x) => x.msg_id === n.msg_id)) return
    const next = [n, ...toasts.value].slice(0, NOTICE_TOAST_MAX)
    toasts.value = next
    dismissTimers.set(n.msg_id, setTimeout(() => dismiss(n.msg_id), NOTICE_TOAST_MS))
  }

  /** 系统级通知：只在用户点过「开启浏览器通知」后才会有权限。 */
  function systemNotify(n: NoticeItem): void {
    if (perm.value !== 'granted') return
    try {
      const note = new Notification(noticeTitle(n), {
        body: noticeLine(n),
        tag: 'mi-notice-' + n.msg_id,
        lang: 'zh-CN',
      })
      note.onclick = () => {
        window.focus()
        openNotice(n)
        note.close()
      }
    } catch { /* 权限被中途收回时静默 */ }
  }

  function notify(n: NoticeItem): void {
    if (!isFresh(n)) return      // 补跑回来的旧消息只进列表，不震
    pushToast(n)
    systemNotify(n)
  }

  function apply(r: NoticesResp): void {
    if (!r.ok) return
    list.value = [...(r.notices || [])]
    unread.value = r.unread || 0
    lastSync.value = r.last_sync || 0
    err.value = r.error || ''
  }

  async function load(first = false): Promise<void> {
    // 用户可能在地址栏里改过站点权限，每轮顺手同步一次，别一直显示旧结论
    if (typeof window !== 'undefined' && 'Notification' in window) {
      if (Notification.permission !== perm.value) perm.value = Notification.permission
    }
    try {
      const r = await apiGet<NoticesResp>('/api/notices?limit=60')
      apply(r)
      const fresh = (r.notices || []).filter((n) => n.seen === 0 && !known.has(n.msg_id))
      for (const n of fresh) known.add(n.msg_id)
      // 第一次拿到数据只建基线：已有的未读不补弹
      if (!bootstrapped) { bootstrapped = true; return }
      if (first) return
      for (const n of fresh) notify(n)
    } catch { err.value = '网络异常' }
  }

  async function refresh(): Promise<number> {
    loading.value = true
    try {
      const r = await apiPost<NoticesResp>('/api/notices/refresh', {})
      const added = r.new || 0
      // 手动检查是一次明确的用户动作，新到的直接提醒
      const fresh = (r.notices || []).filter((n) => n.seen === 0 && !known.has(n.msg_id))
      for (const n of fresh) known.add(n.msg_id)
      apply(r)
      bootstrapped = true
      for (const n of fresh) notify(n)
      if (fresh.length) devices.toast('收到 ' + fresh.length + ' 条新通知')
      else devices.toast(added ? '通知已更新' : (r.error ? '通知拉取失败' : '暂无新通知'))
      return added
    } catch {
      devices.toast('通知检查失败')
      return 0
    } finally {
      loading.value = false
    }
  }

  async function markAll(): Promise<void> {
    try {
      const r = await apiPost<NoticesResp>('/api/notices/read', {})
      apply(r)
      for (const n of list.value) known.add(n.msg_id)
      toasts.value = []
    } catch { devices.toast('操作失败') }
  }

  async function markOne(msgId: number): Promise<void> {
    try {
      const r = await apiPost<NoticesResp>('/api/notices/read', { ids: [msgId] })
      apply(r)
    } catch { /* 静默：只是少清一个红点 */ }
  }

  /** 点通知：清本条未读，能对上设备就顺手把详情打开。 */
  async function openNotice(n: NoticeItem): Promise<void> {
    void markOne(n.msg_id)
    dismiss(n.msg_id)
    if (n.did && devices.devices[n.did]) {
      devices.setMainTab('devices')
      devices.openDrawer(n.did)
    }
  }

  async function requestPerm(): Promise<NoticePerm> {
    if (!('Notification' in window)) { perm.value = 'unsupported'; return perm.value }
    try {
      perm.value = await Notification.requestPermission()
    } catch { perm.value = 'denied' }
    if (perm.value === 'granted') devices.toast('已开启浏览器通知')
    return perm.value
  }

  function openToast(n: NoticeItem): void { void openNotice(n) }

  function startPolling(): void {
    stopPolling()
    void load(true)
    timer = setInterval(() => { void load() }, NOTICE_POLL_MS)
  }
  function stopPolling(): void {
    if (timer) clearInterval(timer)
    timer = null
    for (const t of dismissTimers.values()) clearTimeout(t)
    dismissTimers.clear()
    toasts.value = []
  }

  return {
    list, unread, lastSync, err, loading, toasts, perm,
    hasUnread, badge,
    load, refresh, markAll, markOne, openNotice, openToast, dismiss,
    requestPerm, startPolling, stopPolling,
  }
})
