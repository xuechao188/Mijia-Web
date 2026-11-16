/* 设备视图的数据类型。
 *
 * 与 services/devices.py 的 device_views() 返回结构一一对应；后端一个字段都不改。
 * 这里只描述「读取到的形状」，字段可能缺失时一律用可选，避免运行时对空设备报错。
 */

export type Size = 'sm' | 'md' | 'lg'

export type Category =
  | 'light' | 'climate-sensor' | 'climate' | 'appliance' | 'purifier'
  | 'cleaner' | 'camera' | 'curtain' | 'outlet' | 'switch'
  | 'sensor' | 'hub' | 'ir' | 'generic'

export interface DeviceSwitch {
  key: string
  label?: string
  siid: number
  piid: number
}

export interface ControlOption {
  v: string | number | boolean
  t: string
}

export interface DeviceControl {
  key: string
  label: string
  unit?: string
  kind: string
  siid: number
  piid: number
  writable: boolean
  readable: boolean
  min?: number
  max?: number
  step?: number
  options?: ControlOption[]
  svc?: string
}

export interface ReadableMeta {
  unit?: string
  [key: string]: unknown
}

/** 红外遥控的自定义按键（云端按键表里的一条）。 */
export interface IrKey {
  id: number | string
  name: string
}

/** 红外遥控的一条命令：动作（turn-on/音量±）、只写属性（模式/设定温度）或按键。
 *  三者都没有回读状态，点了就是发一次码。 */
export interface IrCmd {
  id: string
  kind: 'action' | 'set' | 'key'
  group: string
  label: string
  siid?: number
  aiid?: number
  piid?: number
  value?: unknown
  key_id?: number | string
  name?: string
}

/** 空调温度步进：云端只写不读，界面显示的是本机记的最后一次发送值。 */
export interface IrTemp {
  siid: number
  piid: number
  min: number
  max: number
  step: number
  default: number
}

export interface IrInfo {
  kind: string
  label: string
  keys: IrKey[]
  cmds: IrCmd[]
  temp?: IrTemp | null
  note?: string
}

export interface DeviceView {
  did: string
  name: string
  model?: string
  product?: string
  home?: string
  home_id?: string
  room?: string
  room_id?: string
  online: boolean
  last_seen?: number
  controls?: DeviceControl[]
  readable?: Record<string, ReadableMeta>
  switches?: DeviceSwitch[]
  actions?: unknown[]
  ir?: IrInfo | null
  on?: boolean | null
  on_siid?: number | null
  on_piid?: number | null
}

/** /api/live 的每台设备实时值：键是属性名，值可能是布尔/数字/字符串/枚举。 */
export type LiveState = Record<string, unknown>

/** /api/history 的 series：<did> -> { <key>: [[ts, value], ...] } */
export type SeriesMap = Record<string, Record<string, Array<[number, number]>>>

export interface DeviceGroup {
  id: string
  name: string
  dids: string[]
}

export interface LayoutState {
  sizes: Record<string, Size>
  order: string[]
}

export interface ReadoutEntry {
  key: string
  label: string
  text: string
  value: unknown
  unit: string
  order: number
  primary: boolean
}

export interface CurveEntry {
  key: string
  label: string
  points: Array<[number, number]>
  unit: string
  order: number
  last: string
}
