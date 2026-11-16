/* 天气卡片纯逻辑（Vue 版）。
 *
 * 与 static/weather_card.js 的纯函数部分逐项同源：kindOf / iconSvg /
 * aqiGrade / fieldsFor / tempText / pctText / hourlySeries / hourlyLabels /
 * tempRange。DOM 拼装留给 WeatherCard.vue 与 WeatherDrawer.vue。
 * 三尺寸的信息预算、欧洲 AQI 分档、24 小时温度曲线取样规则全部照搬。
 */
import type { WeatherData, WeatherHour, WeatherSize } from './types'

export const SIZES: WeatherSize[] = ['sm', 'md', 'lg']
export const SIZE_LABELS: Record<WeatherSize, string> = { sm: '小', md: '中', lg: '大' }
export const SIZE_TITLES: Record<WeatherSize, string> = {
  sm: '小卡', md: '中卡', lg: '大卡',
}

export type WeatherKind = 'sun' | 'partly' | 'cloud' | 'fog' | 'rain' | 'snow' | 'storm'

export function kindOf(code: unknown): WeatherKind {
  const c = Number(code)
  if (c === 0 || c === 1) return 'sun'
  if (c === 2) return 'partly'
  if (c === 3) return 'cloud'
  if (c === 45 || c === 48) return 'fog'
  if ((c >= 51 && c <= 67) || (c >= 80 && c <= 82)) return 'rain'
  if ((c >= 71 && c <= 77) || c === 85 || c === 86) return 'snow'
  if (c === 95 || c === 96 || c === 99) return 'storm'
  return 'cloud'
}

export const ICONS: Record<WeatherKind, string> = {
  sun: '<circle cx="12" cy="12" r="4"/>' +
       '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4' +
       'M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  partly: '<circle cx="8" cy="8" r="3"/>' +
          '<path d="M8 1v1.5M2.5 8H1M3.4 3.4l1 1"/>' +
          '<path d="M7 18h10a3.5 3.5 0 0 0 .3-7 5 5 0 0 0-9.5 1.2A3.4 3.4 0 0 0 7 18z"/>',
  cloud: '<path d="M6 18h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 18z"/>',
  rain: '<path d="M6 15h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 15z"/>' +
        '<path d="M8 18l-1 3M12 18l-1 3M16 18l-1 3"/>',
  snow: '<path d="M6 15h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 15z"/>' +
        '<path d="M8 19h.01M12 20h.01M16 19h.01"/>',
  fog: '<path d="M5 9h14M3 13h18M6 17h12"/>',
  storm: '<path d="M6 15h12a4 4 0 0 0 .4-8 6 6 0 0 0-11.5 1.5A3.5 3.5 0 0 0 6 15z"/>' +
         '<path d="M13 16l-3 4h3l-1 3"/>',
}

export function iconSvg(kind: WeatherKind | string, px?: number): string {
  const p = ICONS[kind as WeatherKind] || ICONS.cloud
  const n = px || 24
  return '<svg class="wc-icon" width="' + n + '" height="' + n +
         '" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
         'stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" ' +
         'aria-hidden="true">' + p + '</svg>'
}

export interface AqiGrade { level: number; label: string; text: string }

/** Open-Meteo 给的是欧洲 AQI，按欧标分档，不套中国 AQI 阈值。 */
export function aqiGrade(aqi: unknown): AqiGrade {
  if (aqi === null || aqi === undefined || aqi === '' || !isFinite(Number(aqi))) {
    return { level: 0, label: '--', text: 'AQI --' }
  }
  const v = Number(aqi)
  const bands: Array<[number, string]> = [
    [20, '优'], [40, '良'], [60, '中等'], [80, '较差'], [100, '差'],
  ]
  let label = '很差'
  let level = 6
  for (let i = 0; i < bands.length; i++) {
    if (v <= bands[i][0]) { label = bands[i][1]; level = i + 1; break }
  }
  return { level, label, text: 'AQI ' + Math.round(v) + ' · ' + label }
}

export type WeatherField =
  'temp' | 'text' | 'feels' | 'range' | 'aqi' | 'wind' |
  'humidity' | 'pop' | 'sun' | 'hourly'

export const FIELDS: Record<WeatherSize, WeatherField[]> = {
  sm: ['temp', 'text'],
  md: ['temp', 'text', 'feels', 'range', 'aqi', 'wind'],
  lg: ['temp', 'text', 'feels', 'range', 'aqi', 'wind',
       'humidity', 'pop', 'sun', 'hourly'],
}

export function fieldsFor(size: WeatherSize | string): WeatherField[] {
  return (FIELDS[size as WeatherSize] || FIELDS.md).slice()
}

export function tempText(v: unknown, digits?: number): string {
  if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '--'
  return Number(v).toFixed(digits === undefined ? 0 : digits)
}

export function pctText(v: unknown): string {
  if (v === null || v === undefined || v === '' || !isFinite(Number(v))) return '--'
  return Math.round(Number(v)) + '%'
}

/** sparkline 要的是 [[x,y],...]；x 用序号，标签由 hourlyLabels 给。 */
export function hourlySeries(w: WeatherData | null | undefined): Array<[number, number]> {
  const out: Array<[number, number]> = []
  const h = (w && w.hourly) || []
  for (let i = 0; i < h.length; i++) {
    const v = h[i] && h[i].temp
    if (v !== null && v !== undefined && isFinite(Number(v))) {
      out.push([i, Number(v)])
    }
  }
  return out
}

export function hourlyLabels(w: WeatherData | null | undefined): [string, string] {
  const h = (w && w.hourly) || []
  return [h.length ? (h[0].time || '') : '', h.length ? (h[h.length - 1].time || '') : '']
}

export function tempRange(w: WeatherData | null | undefined): { min: number | null; max: number | null } {
  const pts = hourlySeries(w)
  if (!pts.length) return { min: null, max: null }
  const vals = pts.map((p) => p[1])
  return { min: Math.min(...vals), max: Math.max(...vals) }
}

/* ---------- 以下把旧 DOM 拼装里的「算什么」抽成纯函数，组件只渲染结果 ---------- */

export interface WeatherMetric { key: WeatherField; label: string; value: string }

export function weatherMetrics(w: WeatherData | null | undefined, fields: WeatherField[]): WeatherMetric[] {
  const today = (w && w.today) || {}
  const g = aqiGrade(w && w.aqi)
  const rows: WeatherMetric[] = [
    { key: 'feels', label: '体感', value: tempText(w && w.feels, 0) + '°' },
    { key: 'range', label: '今日', value: tempText(today.tmin, 0) + ' / ' + tempText(today.tmax, 0) + '°' },
    { key: 'aqi', label: '空气', value: g.label },
    { key: 'wind', label: '风速', value: tempText(w && w.wind, 0) + ' km/h' },
    { key: 'humidity', label: '湿度', value: pctText(w && w.humidity) },
    { key: 'pop', label: '降水', value: pctText(today.pop_max) },
    { key: 'sun', label: '日照', value: (today.sunrise || '--') + '–' + (today.sunset || '--') },
  ]
  return rows.filter((r) => fields.includes(r.key))
}

export function weatherCardClass(w: WeatherData | null | undefined, size: WeatherSize): string {
  const kind = kindOf(w && w.code)
  return 'device-card weather-card sz-' + size + ' cat-weather wc-' + kind +
    ((w && w.is_day === 0) ? ' wc-night' : '')
}

export function weatherFoot(w: WeatherData | null | undefined): string {
  if (w && w.unavailable) return '天气暂不可用 · 稍后自动重试'
  if (w && w.stale) return '数据未更新'
  return w && w.updated ? '更新于 ' + w.updated : ''
}

export function weatherHero(w: WeatherData | null | undefined): string {
  return ((w && w.city) || '') + ' · ' + ((w && w.text) || '--') +
    ' · 体感 ' + tempText(w && w.feels, 0) + '°'
}

export interface DrawerReadout { label: string; value: string; primary: boolean }

export function drawerReadouts(w: WeatherData | null | undefined): DrawerReadout[] {
  const today = (w && w.today) || {}
  const rows: Array<[string, string, boolean?]> = [
    ['今日最高', tempText(today.tmax, 0) + '°', true],
    ['今日最低', tempText(today.tmin, 0) + '°'],
    ['湿度', pctText(w && w.humidity)],
    ['风速', tempText(w && w.wind, 0) + ' km/h'],
    ['空气质量', aqiGrade(w && w.aqi).text],
    ['降水概率', pctText(today.pop_max)],
    ['日出', today.sunrise || '--'],
    ['日落', today.sunset || '--'],
  ]
  return rows.map((r) => ({ label: r[0], value: r[1], primary: Boolean(r[2]) }))
}

/** 抽屉逐时条：旧版每 3 小时取一个点。 */
export function hourStrip(w: WeatherData | null | undefined): Array<{ time: string; temp: string; pop: string }> {
  const hours: WeatherHour[] = (w && w.hourly) || []
  const out: Array<{ time: string; temp: string; pop: string }> = []
  for (let i = 0; i < hours.length; i += 3) {
    const p = hours[i]
    out.push({ time: p.time || '', temp: tempText(p.temp, 0) + '°', pop: pctText(p.pop) })
  }
  return out
}

export const WEATHER_NOTE = '数据来源 Open-Meteo · 10 分钟刷新 · 空气质量采用欧洲 AQI 标准'
export const WEATHER_FALLBACK: WeatherData = {
  city: '', unavailable: true, text: '天气暂不可用', code: 3,
}
