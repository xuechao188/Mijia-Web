/* 设备类别与卡片尺寸判定（Vue 版）。
 *
 * 与 static/cards.js 逐条同源；测试会把两版的 categoryOf/sizeOf/toggleable
 * 在同一批样本上比对，防止迁移漂移。判定顺序仍是：
 *   1) 型号/产品名决定主功能 -> 决定卡片长什么样；
 *   2) 能力只在型号认不出时兜底分类；
 *   3) 传感器读数与趋势曲线是通用能力，叠加到任何类别上。
 */
import type { Category, DeviceView, Size } from './types'

export const CATEGORY_LABELS: Record<Category, string> = {
  light: '灯光', 'climate-sensor': '环境', climate: '空调',
  appliance: '厨电', purifier: '净化', cleaner: '清洁',
  camera: '安防', curtain: '窗帘', outlet: '插座', switch: '开关',
  sensor: '传感器', hub: '网关', ir: '红外遥控', generic: '设备',
}

export const CURVE_KEYS = [
  'temperature', 'humidity', 'illumination', 'power', 'voltage',
  'current', 'filter_life', 'pm2.5-density', 'co2-density',
]

/** 只有以开/关为主控能力的品类才在卡片与详情显示电源开关。 */
export const TOGGLE_CATS: Partial<Record<Category, 1>> = {
  light: 1, outlet: 1, switch: 1, climate: 1, appliance: 1, curtain: 1,
}

/** 统计条的分组：把十几个细类收成用户嘴里的四类。
 *  照明包括开关（墙面开关、通断器）与灯具；环境是温湿度、空调、净化；
 *  传感器只放纯探测器；其余（插座、窗帘、厨电、摄像头…）归「其它」。 */
export type StatGroup = 'light' | 'env' | 'sensor' | 'other'
export const STAT_GROUPS: Array<[StatGroup, string]> = [
  ['light', '照明'], ['env', '环境'], ['sensor', '传感器'], ['other', '其它'],
]

export function statGroupOf(d: DeviceView | null | undefined): StatGroup {
  const c = categoryOf(d)
  if (c === 'light' || c === 'switch') return 'light'
  if (c === 'climate-sensor' || c === 'climate' || c === 'purifier') return 'env'
  if (c === 'sensor') return 'sensor'
  return 'other'
}

/** 红外遥控：虚拟设备，控制面是「命令 + 自定义按键」，没有电源位。
 *  判定按型号前缀，不看产品名——产品名是多语言描述，型号才是稳定的。 */
export function isIr(d: DeviceView | null | undefined): boolean {
  const m = String((d && d.model) || '').toLowerCase()
  const did = String((d && d.did) || '')
  return m.indexOf('miir.') === 0 || did.indexOf('ir.') === 0 || Boolean(d && d.ir)
}

/** 这台红外遥控能点几下：命令表优先，没有命令表就是自定义按键。 */
export function irActionCount(d: DeviceView | null | undefined): number {
  const blk = d && d.ir
  if (!blk) return 0
  return (blk.cmds || []).length || (blk.keys || []).length
}

const LARGE: Category[] = ['climate-sensor', 'climate', 'purifier', 'cleaner', 'appliance']
const MEDIUM: Category[] = ['light', 'camera', 'curtain']

// 顺序不可随意调整：先具体家电，后泛化关键字（switch/sensor 会吃掉很多型号）
const MODEL_RULES: Array<[RegExp, Category]> = [
  // 红外遥控必须排在第一位：miir.light.ir01 会被下面的 /light/ 抢走，
  // miir.aircondition.ir02 会被 /aircondition/ 判成空调——它们其实是遥控器。
  [/^miir\.|^ir\.|红外遥控/, 'ir'],
  [/sensor_ht|sensor\.ht|thermo|hygro|temp.?humid|miaomiaoce|温湿度/, 'climate-sensor'],
  [/acpartner|aircondition|air.?con|空调/, 'climate'],
  [/fryer|oven|hood|washer|cooker|microwave|kettle|rice|dishwasher|st701|蒸烤|洗衣|油烟|空气炸/, 'appliance'],
  [/purifier|airfresh|new.?wind|waterpuri|新风|净化|净水/, 'purifier'],
  [/vacuum|rockrobo|sweeper|robot.?clean|扫地/, 'cleaner'],
  [/camera|cateye|loock|lock|doorlock|摄像|猫眼|门锁/, 'camera'],
  [/curtain|wcurtain|dooya|窗帘/, 'curtain'],
  [/light|yeelink|philips\.|zbmesh|giot\.|bulb|lamp|strip|灯带|筒灯|台灯/, 'light'],
  [/plug|outlet|socket|valve|插排|插座|通断|水阀/, 'outlet'],
  [/switch|ctrl_neutral|mesw|btsw|kg03hl|wall.?switch|开关/, 'switch'],
  [/sensor|motion|magnet|smoke|gas|occupy|人体|门磁/, 'sensor'],
  [/router|gateway|hub|wifi|repeater|miir\.|remote\.ir|网关|路由/, 'hub'],
]

function keysOf(d: DeviceView | null | undefined): string[] {
  return ((d && d.controls) || []).map((c) => c.key)
}

export function hasCurve(d: DeviceView | null | undefined): boolean {
  const reads = Object.keys((d && d.readable) || {})
  return reads.some((k) => CURVE_KEYS.indexOf(k) >= 0)
}

export function categoryOf(d: DeviceView | null | undefined): Category {
  if (!d) return 'generic'
  // 只看型号与产品名：设备名是用户自定义的（比如把开关叫「客厅灯」）
  const m = ((d.model || '') + ' ' + (d.product || '')).toLowerCase()
  for (const [re, cat] of MODEL_RULES) {
    if (re.test(m)) return cat
  }

  const keys = keysOf(d)
  const reads = Object.keys(d.readable || {})
  const sws = (d.switches || []).length
  // 目标温度控件决定「空调」还是「厨电」（量程 > 50 的是烤箱/炸锅）
  const target = (d.controls || []).find((c) => c.key === 'target-temperature')
  if (keys.indexOf('brightness') >= 0 || keys.indexOf('color-temperature') >= 0) {
    return 'light'
  }
  if (target) return (target.max && target.max > 50) ? 'appliance' : 'climate'
  if (keys.indexOf('fan-level') >= 0) return 'climate'
  if (!sws && (reads.indexOf('temperature') >= 0 || reads.indexOf('humidity') >= 0)) {
    return 'climate-sensor'
  }
  if (reads.indexOf('power') >= 0 || reads.indexOf('voltage') >= 0 ||
      reads.indexOf('current') >= 0) return 'outlet'
  if (sws >= 2) return 'switch'
  return 'generic'
}

/** 设备是否应在卡片/详情展示电源开关：类型以开关为主控，且确有开关属性。 */
export function toggleable(d: DeviceView | null | undefined): boolean {
  if (!d) return false
  if (!TOGGLE_CATS[categoryOf(d)]) return false
  return ((d.switches || []).length > 0)
}

export function sizeOf(d: DeviceView | null | undefined): Size {
  if (!d) return 'sm'
  const c = categoryOf(d)
  const keys = keysOf(d)
  // 离线设备的控件整块不渲染，能摆的只剩图标/名称/离线/最后读数
  if (d.online === false) {
    const hasRead = keys.length > 0 || Object.keys(d.readable || {}).length > 0
    return hasRead ? 'md' : 'sm'
  }
  // 红外遥控：有命令或按键才给中卡（摆一排按钮），否则单格
  if (c === 'ir') return irActionCount(d) > 0 ? 'md' : 'sm'
  if (c === 'light') {
    const lightCtrls = ['brightness', 'color-temperature'].filter((k) => keys.indexOf(k) >= 0).length
    if (lightCtrls >= 2) return 'lg'
    if (lightCtrls === 1) return 'md'
  }
  if (LARGE.indexOf(c) >= 0) {
    const parsed = Array.isArray(d.controls) && d.readable !== undefined
    if (parsed && !hasCurve(d) && keys.length < 2) return 'md'
    return 'lg'
  }
  if (hasCurve(d)) return 'lg'
  if (MEDIUM.indexOf(c) >= 0) return 'md'
  if ((d.switches || []).length >= 2) return 'md'
  if (keys.length >= 2) return 'md'
  return 'sm'
}
