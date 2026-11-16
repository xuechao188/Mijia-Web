/* 读数、中文标签、曲线与卡片控件预算（Vue 版）。
 *
 * 与 static/card_types.js 的纯函数部分同源。DOM 装饰逻辑（decorate）不再
 * 在这里操作元素，而是拆成 content.ts 的 cardContent()，让组件只负责渲染。
 * 这样 Vue 的 diff 不必重建整张卡，3 秒轮询也不会打断正在拖的滑杆。
 */
import { CURVE_KEYS } from './cards'
import { optionLabel } from './labels'
import type {
  Category, CurveEntry, DeviceControl, DeviceSwitch, DeviceView,
  LiveState, ReadoutEntry, Size,
} from './types'

interface ReadoutMeta {
  label: string
  unit: string
  digits: number
  order: number
  bool?: [string, string]
}

export const READOUTS: Record<string, ReadoutMeta> = {
  temperature: { label: '温度', unit: '°C', digits: 1, order: 1 },
  humidity: { label: '湿度', unit: '%', digits: 0, order: 2 },
  power: { label: '功率', unit: 'W', digits: 1, order: 3 },
  voltage: { label: '电压', unit: 'V', digits: 1, order: 4 },
  current: { label: '电流', unit: 'A', digits: 2, order: 5 },
  illumination: { label: '照度', unit: 'lx', digits: 0, order: 6 },
  battery_level: { label: '电量', unit: '%', digits: 0, order: 7 },
  filter_life: { label: '滤芯', unit: '%', digits: 0, order: 8 },
  'pm2.5-density': { label: 'PM2.5', unit: 'μg/m³', digits: 0, order: 9 },
  'co2-density': { label: 'CO₂', unit: 'ppm', digits: 0, order: 10 },
  brightness: { label: '亮度', unit: '%', digits: 0, order: 11 },
  'color-temperature': { label: '色温', unit: 'K', digits: 0, order: 12 },
  'target-temperature': { label: '目标温度', unit: '°C', digits: 0, order: 13 },
  'fan-level': { label: '风速', unit: '', digits: 0, order: 14 },
  'speed-level': { label: '风速', unit: '%', digits: 0, order: 15 },
  volume: { label: '音量', unit: '%', digits: 0, order: 16 },
  'off-delay-time': { label: '延时关机', unit: '分', digits: 0, order: 17 },
  mode: { label: '模式', unit: '', digits: 0, order: 18 },
  motion: { label: '人体', unit: '', digits: 0, order: 19, bool: ['无人', '有人'] },
  contact: { label: '门窗', unit: '', digits: 0, order: 20, bool: ['闭合', '断开'] },
  'vertical-swing': { label: '上下摆风', unit: '', digits: 0, order: 21, bool: ['关', '开'] },
  'horizontal-swing': { label: '左右摇头', unit: '', digits: 0, order: 22, bool: ['关', '开'] },
}

export const UNIT_MAP: Record<string, string> = {
  celsius: '°C', percentage: '%', lux: 'lx', watt: 'W',
  volt: 'V', ampere: 'A', kelvin: 'K', minutes: '分',
}

// spec 的 description 是英文显示名，这里翻成中文（只影响展示，不改云端）
export const PRODUCT_RULES: Array<[RegExp, string]> = [
  [/温湿度|humidity|thermo|hygro/i, '温湿度计'],
  [/water.?puri|净水/i, '净水器'],
  [/air.?fryer|fryer|空气炸/i, '空气炸锅'],
  [/hood|油烟/i, '吸油烟机'],
  [/washer|洗衣/i, '洗衣机'],
  [/three.?key|三键|三开/i, '三键开关'],
  [/two.?key|双键/i, '双键开关'],
  [/wall.?switch|墙壁开关|switch service/i, '墙壁开关'],
  [/vacuum|robot|扫地/i, '扫地机器人'],
  [/purifier|净化/i, '净化器'],
  [/camera|摄像/i, '摄像机'],
  [/lock|门锁/i, '智能门锁'],
  [/curtain|窗帘/i, '窗帘电机'],
  [/router|路由/i, '路由器'],
  [/gateway|网关/i, '网关'],
  [/repeater|放大器/i, '信号放大器'],
  [/plug|socket|插座|插排/i, '智能插座'],
  [/temperature.?humidity|温湿度/i, '温湿度计'],
  [/motion.?sensor|人体/i, '人体传感器'],
  [/occupancy|存在传感器/i, '存在传感器'],
  [/gas.?sensor|燃气/i, '燃气传感器'],
  [/sensor|传感器/i, '传感器'],
  [/remote.?control|红外遥控/i, '红外遥控器'],
  [/speaker|音箱/i, '智能音箱'],
  [/video.?doorbell|可视门铃/i, '可视门铃'],
  [/toothbrush|牙刷/i, '电动牙刷'],
  [/watch|hand.?band|手表|手环/i, '智能穿戴'],
  [/toilet|马桶/i, '智能马桶盖'],
  [/towel.?rack|毛巾架/i, '电热毛巾架'],
  [/bath.?heater|浴霸/i, '浴霸'],
  [/kettle|水壶/i, '电水壶'],
  [/control.?panel|中控屏/i, '智能中控屏'],
  [/mosquito|驱蚊/i, '智能驱蚊器'],
  [/air.?conditioner|空调/i, '空调'],
  [/outlet|插座/i, '智能插座'],
  [/light|灯/i, '智能灯'],
  [/switch|开关/i, '智能开关'],
  [/valve|阀/i, '智能阀门'],
]

export function labelOf(key: string, d?: DeviceView | null): string {
  if (READOUTS[key]) return READOUTS[key].label
  // 冷门控件：至少用 spec 里自带的中文 label，不要把英文 key 露在卡片上
  for (const c of (d && d.controls) || []) {
    if (c.key === key && c.label) return c.label
  }
  return key
}

export function unitOf(key: string, d?: DeviceView | null): string {
  const meta = ((d && d.readable) || {})[key]
  const raw = meta && meta.unit
  if (raw && UNIT_MAP[String(raw).toLowerCase()]) return UNIT_MAP[String(raw).toLowerCase()]
  if (raw && /^[^\w\s]{1,4}$/.test(String(raw))) return String(raw)
  for (const c of (d && d.controls) || []) {
    if (c.key === key && c.unit) return c.unit
  }
  return (READOUTS[key] && READOUTS[key].unit) || ''
}

export function formatValue(key: string, v: unknown, d?: DeviceView | null): string {
  if (v === undefined || v === null) return ''
  const meta = READOUTS[key] || ({} as ReadoutMeta)
  if (typeof v === 'boolean' || meta.bool) {
    return meta.bool ? meta.bool[v ? 1 : 0] : (v ? '开' : '关')
  }
  if (typeof v !== 'number' || !isFinite(v)) return String(v)
  const digits = meta.digits === undefined ? 1 : meta.digits
  let s = v.toFixed(digits)
  if (/\.0+$/.test(s)) s = s.replace(/\.0+$/, '')
  return s + (unitOf(key, d) || '')
}

export function productLabel(d: DeviceView | null | undefined): string {
  const p = ((d && d.product) || '').trim()
  for (const [re, label] of PRODUCT_RULES) {
    if (re.test(p)) return label
  }
  if (p && /[\u4e00-\u9fa5]/.test(p)) return p
  if (p && !/^[a-z0-9._\-\s]+$/i.test(p)) return p
  return ''
}

export function switchLabel(s: DeviceSwitch | null | undefined, i: number): string {
  const t = String((s && s.label) || '').toLowerCase()
  if (/left|左/.test(t)) return '左键'
  if (/middle|center|中/.test(t)) return '中键'
  if (/right|右/.test(t)) return '右键'
  if (/toggle|切换/.test(t)) return '切换'
  if (/^on\d+$/.test(t) || /switch service|switch$/.test(t)) return '按键 ' + (i + 1)
  return (s && s.label) || ('按键 ' + (i + 1))
}

export function pickControl(d: DeviceView | null | undefined, key: string): DeviceControl | null {
  for (const c of (d && d.controls) || []) if (c.key === key) return c
  return null
}

/** 摄像头参数是「控件」而非传感器读数，不进读数区，避免出现「夜视 0」。 */
export function isCameraCtrl(c: DeviceControl): boolean {
  const s = c.svc || ''
  return s.indexOf('camera-control') >= 0
    || s.indexOf('video-doorbell') >= 0
    || s.indexOf('motion-detection') >= 0
}

/** 有实时值的读数，按优先级排序；卡片与抽屉共用。 */
export function readoutEntries(d: DeviceView, live: LiveState): ReadoutEntry[] {
  const keys = Object.keys((d && d.readable) || {})
  for (const c of (d && d.controls) || []) {
    if (c.readable && !isCameraCtrl(c) && keys.indexOf(c.key) < 0) keys.push(c.key)
  }
  const out: ReadoutEntry[] = []
  for (const k of keys) {
    if (!Object.prototype.hasOwnProperty.call(live || {}, k)) continue
    const v = live[k]
    if (v === null || v === undefined) continue
    const meta = READOUTS[k] || ({} as ReadoutMeta)
    out.push({
      key: k, label: labelOf(k, d), text: readoutText(d, k, v),
      value: v, unit: unitOf(k, d),
      order: meta.order || 90, primary: k === 'temperature',
    })
  }
  out.sort((a, b) => a.order - b.order)
  return out
}

/** 读数文本：枚举控件取选项中文名，避免把「模式」显示成裸数字或英文模式名。 */
export function readoutText(d: DeviceView, key: string, v: unknown): string {
  const c = pickControl(d, key)
  if (c && c.kind === 'enum' && c.options && c.options.length) {
    for (const o of c.options) if (o.v === v) return optionLabel(key, o.t)
  }
  return formatValue(key, v, d)
}

/** 有历史点的曲线，按优先级排序。只画这台设备当前确实具备的读数。 */
export function curveEntries(d: DeviceView, series: Record<string, Array<[number, number]>>): CurveEntry[] {
  const out: CurveEntry[] = []
  const allowed = Object.keys((d && d.readable) || {})
  for (const c of (d && d.controls) || []) {
    if (c.readable && allowed.indexOf(c.key) < 0) allowed.push(c.key)
  }
  for (const k in series || {}) {
    if (!Object.prototype.hasOwnProperty.call(series, k)) continue
    if (CURVE_KEYS.indexOf(k) < 0) continue
    if (allowed.length && allowed.indexOf(k) < 0) continue
    const pts = series[k] || []
    if (pts.length < 2) continue
    const meta = READOUTS[k] || ({} as ReadoutMeta)
    out.push({
      key: k, label: labelOf(k), points: pts, unit: unitOf(k, d),
      order: meta.order || 90,
      last: formatValue(k, pts[pts.length - 1][1], d),
    })
  }
  out.sort((a, b) => a.order - b.order)
  return out
}

export interface SparkOptions { w?: number; h?: number; color?: string }

/** 生成内联 SVG 折线（纯字符串，卡片与抽屉共用）。 */
export function sparkline(points: Array<[number, number]> | null | undefined, opt: SparkOptions = {}): string {
  const w = opt.w || 240, h = opt.h || 52, pad = 4
  const pts = (points || []).filter((p) => p && isFinite(p[0]) && isFinite(p[1]))
  if (!pts.length) return ''
  const vals = pts.map((p) => p[1])
  let lo = Math.min(...vals), hi = Math.max(...vals)
  if (hi - lo < 1e-9) { lo -= 1; hi += 1 }
  const span = hi - lo
  const xy = pts.map((p, i) => {
    const x = pts.length === 1 ? w / 2 : pad + i / (pts.length - 1) * (w - pad * 2)
    const y = h - pad - (p[1] - lo) / span * (h - pad * 2)
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10]
  })
  const line = xy.map((p) => p[0] + ',' + p[1]).join(' ')
  const area = 'M' + xy[0][0] + ',' + (h - pad) + ' L'
    + xy.map((p) => p[0] + ',' + p[1]).join(' L')
    + ' L' + xy[xy.length - 1][0] + ',' + (h - pad) + ' Z'
  const color = opt.color || 'var(--accent)'
  const id = 'g' + Math.random().toString(36).slice(2, 8)
  return '<svg class="ct-svg" viewBox="0 0 ' + w + ' ' + h + '" '
    + 'preserveAspectRatio="none" role="img" aria-label="趋势曲线">'
    + '<defs><linearGradient id="' + id + '" x1="0" y1="0" x2="0" y2="1">'
    + '<stop offset="0%" stop-color="' + color + '" stop-opacity="0.26"/>'
    + '<stop offset="100%" stop-color="' + color + '" stop-opacity="0"/>'
    + '</linearGradient></defs>'
    + '<path d="' + area + '" fill="url(#' + id + ')"/>'
    + '<polyline points="' + line + '" fill="none" stroke="' + color
    + '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>'
    + '<circle cx="' + xy[xy.length - 1][0] + '" cy="' + xy[xy.length - 1][1]
    + '" r="2.6" fill="' + color + '"/></svg>'
}

/** 卡片上按类别铺哪些专属滑杆/步进；小卡一律不铺。 */
export function cardControls(d: DeviceView, cat: Category, size: Size): DeviceControl[] {
  if (size === 'sm') return []
  const out: DeviceControl[] = []
  const pushRange = (c: DeviceControl | null): void => {
    if (c && c.writable && c.kind === 'range') out.push(c)
  }
  if (cat === 'light') {
    pushRange(pickControl(d, 'brightness'))
    if (size === 'lg') pushRange(pickControl(d, 'color-temperature'))
  } else if (cat === 'climate' || cat === 'appliance') {
    pushRange(pickControl(d, 'target-temperature'))
    if (size === 'lg') pushRange(pickControl(d, 'fan-level') || pickControl(d, 'speed-level'))
  } else if (cat === 'purifier' || cat === 'cleaner' || cat === 'curtain') {
    if (size === 'lg') pushRange(pickControl(d, 'mode'))
  }
  return out
}
