/* 卡片模型：把 static/app.js 的 baseCard + card_types.js 的 decorate
 * 里所有「决定显示什么」的分支，收敛成一个纯函数 buildCard()。
 *
 * 旧界面是命令式拼 DOM，每 3 秒轮询整张卡重建一次；Vue 版只重算这个
 * 模型，由组件 diff 局部更新，滑杆拖动与抽屉不会被重建打断。
 * 内容预算（固定行高下能放几块）与 P0 修复全部保留：
 *   - 名称两行 + 状态区重排、离线不渲染任何控件
 *   - 小卡只把一项有单位/布尔的读数并进副标题（不出现「已关闭 · 0」）
 *   - 中卡只放一块内容、有大卡才放曲线、多键开关不叠读数
 *   - 除头部外没有实质内容块时收成单格（is-bare）
 */
import { CATEGORY_LABELS, STAT_GROUPS, categoryOf, hasCurve, irActionCount, sizeOf, statGroupOf, toggleable } from './cards'
import { matches } from './groups'
import { optionLabel } from './labels'
import {
  READOUTS, cardControls, curveEntries, productLabel, readoutEntries,
  switchLabel,
} from './readouts'
import type {
  Category, CurveEntry, DeviceControl, DeviceGroup, DeviceSwitch, DeviceView,
  IrCmd, LayoutState, LiveState, ReadoutEntry, Size,
} from './types'

export interface ChipAction {
  key: string
  label: string
  control: DeviceControl
  value: unknown
  active: boolean
  swing?: boolean
}

export interface CardModel {
  did: string
  cat: Category
  size: Size
  offline: boolean
  name: string
  isOn: boolean
  multi: boolean
  showSwitch: boolean
  /** 副标题：状态优先，没状态就用房间/产品；纯上下文不画状态点。 */
  subText: string
  subIsStatus: boolean
  switches: DeviceSwitch[]
  switchMore: number
  chips: ChipAction[]
  /** 红外遥控的命令按钮（点一下发一次码，没有状态）。 */
  ir: IrCmd[]
  reads: ReadoutEntry[]
  ctrls: DeviceControl[]
  curves: CurveEntry[]
  curveHint: string
  bare: boolean
  /** 大卡有分类内容时，四行档案压成一行。 */
  info: string
  detailRows: Array<[string, string]>
}

export interface BuildOptions {
  live: LiveState
  history: Record<string, Array<[number, number]>>
  names: Record<string, string>
  metrics: string[]
  sizes: Record<string, Size>
  homesCount: number
}

export function displayName(d: DeviceView, names: Record<string, string>): string {
  return names[String(d.did)] || d.name
}

export function cardSize(d: DeviceView, sizes: Record<string, Size>): Size {
  return sizes[String(d.did)] || sizeOf(d)
}

/** 卡片状态文案：只说有意义的话，不再把「运行中 · 在线 · 温度」堆成一行。 */
export function cardStatus(d: DeviceView, o: {
  multi: boolean; sws: DeviceSwitch[]; isOn: boolean; offline: boolean; live: LiveState
}): string {
  if (o.offline) return '离线'
  if (o.multi) {
    const n = o.sws.filter((s) => o.live[s.key] === true).length
    return n + '/' + o.sws.length + ' 路开'
  }
  if (!toggleable(d)) return ''
  if (o.isOn) return '已开启'
  return o.live.on === false ? '已关闭' : '状态未知'
}

/** 没有状态可说的设备用「房间」当第二行；多家庭并存时带家庭名。 */
export function cardContext(d: DeviceView, homesCount: number): string {
  const room = (d.room || '').trim()
  if (!room) return productLabel(d) || ''
  return (homesCount > 1 && d.home) ? d.home + ' · ' + room : room
}

export function relTime(ts: number): string {
  const s = (Date.now() / 1000) - ts
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + ' 分钟前'
  if (s < 86400) return Math.round(s / 3600) + ' 小时前'
  return Math.round(s / 86400) + ' 天前'
}

/** 卡片上除了图标 + 名称 + 状态还有没有别的内容（抽屉收口提示用）。 */
export function cardHasContent(d: DeviceView, live: LiveState): boolean {
  if (readoutEntries(d, live).length) return true
  if (!d.online) return false
  if (d.ir && irActionCount(d) > 0) return true
  const ctrls = (d.controls || []).filter((c) => c.writable)
  return ctrls.length > 0 || (d.switches || []).length > 1
}

/** 按拖拽顺序稳定排序（未拖拽过的设备保持默认相对顺序排末尾）。 */
export function applyOrder<T extends DeviceView>(list: T[], order: string[]): T[] {
  const pos = new Map<string, number>(order.map((did, i) => [String(did), i]))
  return list.slice().sort((a, b) => {
    const ia = pos.has(String(a.did)) ? (pos.get(String(a.did)) as number) : 1e9
    const ib = pos.has(String(b.did)) ? (pos.get(String(b.did)) as number) : 1e9
    return ia !== ib ? ia - ib : 0
  })
}

/** 在线优先：能控制的设备排前面，离线沉底；两组内部各自保持既有顺序。
 *  离线卡片的控件本来就不渲染，堆在首屏只会把可用设备挤到第二屏。 */
export function onlineFirst<T extends DeviceView>(list: T[]): T[] {
  const up: T[] = []
  const down: T[] = []
  for (const d of list) (d.online ? up : down).push(d)
  return up.concat(down)
}

export function visibleDevices(
  devices: DeviceView[],
  filter: string,
  groups: DeviceGroup[],
  kw: string,
  layout: LayoutState,
  names: Record<string, string>,
): DeviceView[] {
  const needle = (kw || '').toLowerCase()
  const list = devices.filter((d) => {
    if (!matches(filter, d, groups)) return false
    if (needle) {
      const hay = (displayName(d, names) + ' ' + d.name + ' ' +
        (d.model || '') + ' ' + (d.product || '') + ' ' +
        (d.home || '') + ' ' + (d.room || '')).toLowerCase()
      if (!hay.includes(needle)) return false
    }
    return true
  })
  return onlineFirst(applyOrder(list, layout.order))
}

export interface StatGroupCount {
  key: string
  label: string
  count: number
  /** 该组里正在运行（任一路开着）的台数 */
  on: number
}

export function deviceOn(d: DeviceView, bucket: LiveState): boolean {
  const sws = d.switches || []
  return sws.length > 1 ? sws.some((s) => bucket[s.key] === true) : bucket.on === true
}

export function statCounts(devices: DeviceView[], live: Record<string, LiveState>) {
  let online = 0, on = 0
  for (const d of devices) {
    if (d.online) online++
    if (deviceOn(d, live[d.did] || {})) on++
  }
  return { total: devices.length, online, on }
}

/** 统计条的类型读数：只返回本范围内真实存在的组，空组不占格子。
 *  顺序固定为 照明 → 环境 → 传感器 → 其它，跨房间切换时格子不跳位。 */
export function statGroups(
  devices: DeviceView[], live: Record<string, LiveState>,
): StatGroupCount[] {
  const acc = new Map<string, { count: number; on: number }>()
  for (const d of devices) {
    const k = statGroupOf(d)
    const b = acc.get(k) || { count: 0, on: 0 }
    b.count++
    if (deviceOn(d, live[d.did] || {})) b.on++
    acc.set(k, b)
  }
  const out: StatGroupCount[] = []
  for (const [key, label] of STAT_GROUPS) {
    const b = acc.get(key)
    if (b) out.push({ key, label, count: b.count, on: b.on })
  }
  return out
}

/** 统计条口子按下去之后的范围：'' = 全部，'online' = 只看在线，
 *  其余是类型分组 key（light / env / sensor / other）。
 *  它叠加在家庭 / 房间 / 搜索之上，是第二维筛选，所以不进 filter 键。 */
export const STAT_FILTER_ONLINE = 'online'

export function matchStat(d: DeviceView, f: string): boolean {
  if (!f) return true
  if (f === STAT_FILTER_ONLINE) return Boolean(d.online)
  return statGroupOf(d) === f
}

export function filterByStat<T extends DeviceView>(list: T[], f: string): T[] {
  if (!f) return list
  return list.filter((d) => matchStat(d, f))
}

/** 卡片上摆哪几个红外按钮：有命令表就用命令表（开关机/音量±…），
 *  自定义遥控没有命令表，直接把前几个按键摆上来。 */
export function irQuick(d: DeviceView, limit = 4): IrCmd[] {
  const blk = d && d.ir
  if (!blk) return []
  const cmds = blk.cmds || []
  if (cmds.length) return cmds.slice(0, limit)
  return (blk.keys || []).slice(0, limit).map((k) => ({
    id: 'k:' + String(k.id), kind: 'key' as const, group: '按键',
    label: k.name, key_id: k.id,
  }))
}

/** 红外卡片的副标题：品类 + 按键数，比「状态未知」有意义。
 *  红外是单向发码，本来就没有开关状态，不能照抄空调/灯具那套。 */
export function irSubText(d: DeviceView): string {
  const blk = d && d.ir
  if (!blk) return ''
  const n = (blk.keys || []).length
  return (blk.label || '红外遥控') + (n ? ' · ' + n + ' 键' : '')
}

function chipActions(d: DeviceView, live: LiveState, allow: boolean): ChipAction[] {
  if (!allow) return []
  const out: ChipAction[] = []
  const seen = new Set<string>()
  for (const c of d.controls || []) {
    if (out.length >= 6) break
    if (!c.writable || seen.has(c.key)) continue
    if (c.kind === 'enum' && (c.key === 'fan-level' || c.key === 'mode')
        && c.options && c.options.length <= 6) {
      seen.add(c.key)
      for (const o of c.options) {
        if (out.length >= 6) break
        out.push({
          key: c.key + ':' + String(o.v), label: optionLabel(c.key, o.t),
          control: c, value: o.v, active: live[c.key] === o.v,
        })
      }
    } else if ((c.key === 'horizontal-swing' || c.key === 'vertical-swing')
               && c.kind === 'bool') {
      seen.add(c.key)
      out.push({
        key: c.key, label: c.key === 'horizontal-swing' ? '↔ 摇头' : '↕ 摆风',
        control: c, value: !live[c.key], active: Boolean(live[c.key]), swing: true,
      })
    }
  }
  return out
}

export function buildCard(d: DeviceView, opt: BuildOptions): CardModel {
  const live = opt.live || {}
  const sws = d.switches || []
  const multi = sws.length > 1
  const isOn = multi ? sws.some((s) => live[s.key] === true) : live.on === true
  const offline = !d.online
  const cat = categoryOf(d)
  const size = cardSize(d, opt.sizes || {})
  const showSwitch = toggleable(d)

  const statusText = cardStatus(d, { multi, sws, isOn, offline, live })
  const contextText = cardContext(d, opt.homesCount || 0)
  let subText = statusText || contextText
  let subIsStatus = Boolean(statusText)
  // 红外遥控没有开关状态，副标题改成「电视遥控 · 97 键」这类可核对的实信息
  if (d.ir && !offline) {
    const t = irSubText(d)
    if (t) { subText = t; subIsStatus = false }
  }

  // 离线设备的控件整块不渲染：点了也不会成功，只会让人以为程序坏了
  const ctrls = offline ? [] : cardControls(d, cat, size)
  const switches = (showSwitch && multi && !offline) ? sws.slice(0, 4) : []
  const switchMore = (showSwitch && multi && !offline && sws.length > 4) ? sws.length - 4 : 0

  const hasSliders = ctrls.length > 0
  const roomForChips = size !== 'sm' && !offline
    && !(multi && showSwitch)
    && !(hasSliders && size === 'md')
  const chips = chipActions(d, live, roomForChips)
  // 红外按钮与枚举 chips 是两套语义：前者是发码，后者是写属性。
  // 红外设备不会有枚举 chips（没有 controls），所以不会抢位置。
  const irCmds = (d.ir && !offline && size !== 'sm') ? irQuick(d, size === 'lg' ? 6 : 4) : []

  let reads = readoutEntries(d, live)
  const picks = opt.metrics || []
  if (picks.length) {
    reads.sort((a, b) => {
      const ai = picks.indexOf(a.key), bi = picks.indexOf(b.key)
      const x = ai < 0 ? 99 : ai, y = bi < 0 ? 99 : bi
      return x !== y ? x - y : a.order - b.order
    })
  }
  if (size !== 'sm' && ctrls.length) {
    const shown = ctrls.map((c) => c.key)
    reads = reads.filter((r) => r.primary || shown.indexOf(r.key) < 0)
  }
  if (size === 'md' && ctrls.length) reads = []
  if (size !== 'sm' && switches.length) reads = []

  // 小卡：只把一项有单位或布尔的读数并进副标题，避免撑高网格
  if (size === 'sm') {
    const pick0 = reads.find((r) => (READOUTS[r.key] && READOUTS[r.key].bool)
      || typeof r.value === 'boolean' || r.unit)
    if (pick0) {
      subText = subText ? subText + ' · ' + pick0.text : pick0.text
      if (!statusText) subIsStatus = false
    }
    reads = []
  } else {
    reads = reads.slice(0, size === 'lg' ? 4 : 2)
  }

  const curves = offline ? [] : curveEntries(d, opt.history || {})
  const shownCurves = size === 'lg' && curves.length && !ctrls.length ? [curves[0]] : []
  const curveHint = (size === 'lg' && !offline && !ctrls.length && !shownCurves.length && hasCurve(d))
    ? '历史曲线采样中…' : ''

  // 除头部以外没有任何实质内容块：收成单格，别让空板子占 2×2
  const bare = size !== 'sm'
    && !reads.length && !ctrls.length && !shownCurves.length
    && !chips.length && !switches.length && !irCmds.length

  const pl = productLabel(d)
  const info = [pl || CATEGORY_LABELS[cat],
    [d.home, d.room].filter(Boolean).join(' / ') || '未分配']
    .filter(Boolean).join(' · ')
  const detailRows: Array<[string, string]> = [
    ['产品', pl || CATEGORY_LABELS[cat] || d.model || '—'],
    ['位置', [d.home, d.room].filter(Boolean).join(' / ') || '未分配'],
    ['型号', d.model || '—'],
    ['状态', (d.online ? '在线' : '离线') + (d.last_seen ? ' · ' + relTime(d.last_seen) : '')],
  ]

  return {
    did: String(d.did), cat, size, offline, name: displayName(d, opt.names || {}),
    isOn, multi, showSwitch, subText, subIsStatus, switches, switchMore,
    chips, ir: irCmds, reads, ctrls, curves: shownCurves, curveHint, bare, info, detailRows,
  }
}

export { switchLabel }
