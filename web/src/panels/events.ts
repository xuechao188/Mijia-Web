/* 事件流纯逻辑（Vue 版）。
 * 与 static/app.js 的 loadEvents() 同源：/api/events 拿最近 50 条，
 * 时间列直接用后端格式化好的 time，正文是 [设备名] + text，
 * type=error 的条目标红。文案拼接保持原样，组件一律用插值而非 innerHTML。
 */
import type { EventItem } from './types'

export const EVENT_EMPTY = '暂无事件'
export const EVENT_TITLE = '事件流'

export function eventTime(e: EventItem): string {
  return e.time || ''
}

export function eventText(e: EventItem): string {
  return (e.name ? '[' + e.name + '] ' : '') + (e.text || '')
}

export function eventTone(e: EventItem): string {
  return e.type === 'error' ? 'err' : ''
}

/** summary 是最近 24 小时按类型计数，后端已返回，这里只做稳定的文本化。 */
export function summaryText(summary: Record<string, number> | null | undefined): string {
  if (!summary) return ''
  const keys = Object.keys(summary).sort()
  if (!keys.length) return ''
  return keys.map((k) => k + ' ' + summary[k]).join(' · ')
}
