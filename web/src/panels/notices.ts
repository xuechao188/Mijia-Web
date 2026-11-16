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
