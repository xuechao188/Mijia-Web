/* 设备通知的纯逻辑（Vue 版）。
 *
 * 数据来自后端 /api/notices —— 它后台轮询米家「消息中心」的未读消息，
 * 按 msg_id 去重后落盘。这里只做三件事：分类文案、正文拼装、提醒语气，
 * 组件一律插值，不拼 HTML。
 */
import type { NoticeItem } from './types'

export const NOTICE_TITLE = '设备通知'
export const NOTICE_EMPTY = '暂无设备通知。门铃、门锁、电量、耗材这类设备提醒会出现在这里。'
export const NOTICE_HINT = '通知来自米家消息中心，只读不改：系统不会替你在手机上标已读。'
export const NOTICE_PERM_ON = '浏览器通知已开启：新消息会推到系统通知中心'
export const NOTICE_PERM_OFF = '开启浏览器通知'
export const NOTICE_PERM_DENIED = '浏览器已屏蔽通知，需在地址栏的网站权限里改回'
export const NOTICE_SYSTEM_UNAVAILABLE = '当前浏览器不支持系统通知'
/* Edge 常把权限请求「静默阻尼」：requestPermission() 不弹框、直接返回 default。
 * 没有反馈时点一下什么都没发生，所以每种结果都要给一句可操作的引导。 */
export const NOTICE_PERM_ASK_DEFAULT = '没弹出授权框？点地址栏左侧图标 → 网站权限 → 通知 → 允许'
export const NOTICE_PERM_ASK_DENIED = '通知被浏览器屏蔽：点地址栏左侧图标 → 网站权限 → 通知 → 允许'
export const NOTICE_PERM_ASK_UNSAFE = '请通过 127.0.0.1 或 localhost 打开，才能开启系统通知'
export const NOTICE_PERM_TOAST_OK = '已开启浏览器通知'
export const NOTICE_PERM_TOAST_DEFAULT = '浏览器没弹出授权框，请在地址栏图标里手动允许通知'

/** 标签筛选的类别：all 表示不过滤；其余对应 noticeKind 的三类。 */
export type NoticeFilter = 'all' | 'device' | 'scene' | 'system'

export const NOTICE_FILTERS: { key: NoticeFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'device', label: '设备消息' },
  { key: 'scene', label: '智能场景' },
  { key: 'system', label: '系统消息' },
]

/** 把一条通知归到某个筛选类别（与 noticeKind 完全同一口径）。 */
export function noticeFilterOf(n: NoticeItem): Exclude<NoticeFilter, 'all'> {
  if (n.kind === 6) return 'device'
  if (n.kind === 13) return 'scene'
  return 'system'
}

/** 按标签过滤；all 直接返回原列表，不产生新数组。 */
export function filterNotices(list: NoticeItem[], filter: NoticeFilter): NoticeItem[] {
  if (filter === 'all') return list
  return list.filter((n) => noticeFilterOf(n) === filter)
}

/** 各类条数，含 all 总数——标签上的数字直接用它。 */
export function noticeCounts(list: NoticeItem[]): Record<NoticeFilter, number> {
  const c: Record<NoticeFilter, number> = { all: list.length, device: 0, scene: 0, system: 0 }
  for (const n of list) c[noticeFilterOf(n)]++
  return c
}

/** 消息类型：米家消息中心的 type 字段，实测 6=设备消息、13=智能/自动化结果。 */
export function noticeKind(n: NoticeItem): string {
  if (n.kind === 6) return '设备消息'
  if (n.kind === 13) return '智能场景'
  return '系统消息'
}

export function noticeTitle(n: NoticeItem): string {
  return (n.title || '').trim() || noticeKind(n)
}

/** 第二行：设备名 · 房间（都缺时退回型号） */
export function noticeSub(n: NoticeItem): string {
  const bits = [n.body, n.room, n.home].filter((x) => Boolean(x && String(x).trim()))
  if (bits.length) return bits.join(' · ')
  return n.model || ''
}

/** 告警类文案标红：电量/超时/异常/告警/失败/低 */
const WARN_WORDS = ['电量低', '低电量', '超时', '异常', '告警', '失败', '未关', '请及时', '离线']

export function noticeTone(n: NoticeItem): string {
  const t = noticeTitle(n)
  return WARN_WORDS.some((w) => t.indexOf(w) >= 0) ? 'warn' : ''
}

/** 系统通知的正文：一句话说清「哪台设备、在哪个房间、发生了什么」。 */
export function noticeLine(n: NoticeItem): string {
  const where = [n.body, n.room].filter((x) => Boolean(x && String(x).trim())).join(' · ')
  return where ? noticeTitle(n) + '｜' + where : noticeTitle(n)
}

/** 相对时间只给一小时内的，再久就直接给时刻，避免「3 天前」这种模糊说法。 */
export function noticeAge(ts: number | undefined, now = Date.now() / 1000): string {
  if (!ts) return ''
  const diff = Math.max(0, now - ts)
  if (diff < 60) return '刚刚'
  if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前'
  return ''
}

/** 只有最近 6 小时内到达的才弹卡片/推系统通知：补跑历史不该连环震。 */
export const NOTICE_FRESH_S = 6 * 3600

export function isFresh(n: NoticeItem, now = Date.now() / 1000): boolean {
  return Boolean(n.ts) && now - Number(n.ts) < NOTICE_FRESH_S
}

/* ---------------- 通知自检：判断系统通知到底卡在哪一层 ---------------- */

export type NotifyDiag = {
  time: string
  ua: string
  origin: string
  secure: boolean
  hasApi: boolean
  permission: string
  queryState: string
  testSent: boolean
  testError: string
  verdict: string
}

export const NOTICE_TEST_TITLE = '米家Web版 · 通知自检'
export const NOTICE_TEST_BODY = '如果你看到这条，说明系统通知通道是通的。'

/**
 * 收集诊断并尝试发一条测试系统通知。
 * 逐层判定：安全上下文 → API 支持 → 权限 → 实际构造/发送。
 * 浏览器差异（尤其 Edge 的静默阻尼与系统级拦截）由 testSent/testError 落地成证据。
 */
export async function runNotifyDiagnostic(): Promise<NotifyDiag> {
  const secure = typeof window !== 'undefined' && 'isSecureContext' in window
    ? Boolean(window.isSecureContext) : false
  const hasApi = typeof window !== 'undefined' && 'Notification' in window
  const origin = typeof location !== 'undefined' ? location.protocol + '//' + location.host : ''
  const ua = typeof navigator !== 'undefined' ? navigator.userAgent : ''
  const permission = hasApi ? Notification.permission : 'unsupported'

  let queryState = 'n/a'
  try {
    if (typeof navigator !== 'undefined' && navigator.permissions?.query) {
      const r = await navigator.permissions.query({ name: 'notifications' as PermissionName })
      queryState = r.state
    }
  } catch { queryState = 'error' }

  let testSent = false
  let testError = ''
  if (!hasApi) {
    testError = '浏览器不支持 Notification API'
  } else if (!secure) {
    testError = '非安全上下文，浏览器拒绝创建通知'
  } else if (permission !== 'granted') {
    testError = '权限不是 granted，跳过发送'
  } else {
    try {
      const note = new Notification(NOTICE_TEST_TITLE, {
        body: NOTICE_TEST_BODY,
        tag: 'mi-notice-test',
        lang: 'zh-CN',
      })
      testSent = true
      setTimeout(() => note.close(), 8000)
    } catch (e) {
      testError = e instanceof Error ? e.message : String(e)
    }
  }

  const verdict = notifyVerdict(
    secure, hasApi, permission, queryState, testSent, testError, ua,
  )

  return {
    time: new Date().toLocaleString('zh-CN'),
    ua, origin, secure, hasApi, permission, queryState,
    testSent, testError, verdict,
  }
}

/**
 * 按操作系统给出「浏览器已接受、但系统没弹横幅」的排查方向。
 * macOS 与 Windows 的通知中心入口和静默开关不同，不能写死一套。
 */
export function notifyPlatformHint(ua: string): string {
  const mac = /Macintosh|Mac OS X/i.test(ua)
  if (mac)
    return '通知可能已进通知中心（点右上角时间查看）。若没弹横幅：检查「专注模式」是否开启，或把通知样式从「横幅」改为「提醒」。'
  return '通知可能已进通知中心（点右下角通知中心查看）。若没弹：检查 Edge 是否被允许发通知，并关闭「专注助手/勿扰模式」。'
}

/** 诊断结论：逐层判定，最后一层按平台给引导。抽成纯函数便于测试。 */
export function notifyVerdict(
  secure: boolean, hasApi: boolean, permission: string, queryState: string,
  testSent: boolean, testError: string, ua: string,
): string {
  if (!secure) return '页面不是安全上下文（需 localhost 或 https）——浏览器会禁用通知。'
  if (!hasApi) return '当前浏览器不提供 Notification API，无法发系统通知。'
  if (permission === 'denied' || queryState === 'denied')
    return '站点通知权限被拒绝（denied）——需在地址栏图标或网站设置里改为「允许」。'
  if (permission === 'default')
    return '权限未授予（default）——Edge 常静默阻尼，需在地址栏图标里手动选「允许」。'
  if (permission === 'granted' && !testSent)
    return '权限已授予但发送失败：' + (testError || '未知错误') + '——多为浏览器/系统层拦截。'
  if (permission === 'granted' && testSent)
    return '浏览器已接受通知请求（不代表系统一定弹出）。' + notifyPlatformHint(ua)
  return '未知状态，请把本诊断发给开发者。'
}

/** 把诊断拼成一段可复制的文字，方便用户直接贴给开发者。 */
export function formatDiag(d: NotifyDiag): string {
  return [
    '【通知自检】' + d.time,
    '浏览器: ' + d.ua,
    '页面: ' + d.origin,
    '安全上下文: ' + d.secure + ' / 支持API: ' + d.hasApi,
    '权限: ' + d.permission + ' / 权限查询: ' + d.queryState,
    '测试通知发出: ' + d.testSent + (d.testError ? ' / 错误: ' + d.testError : ''),
    '结论: ' + d.verdict,
  ].join('\n')
}
