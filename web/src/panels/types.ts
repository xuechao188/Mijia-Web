/* ⑥ 四个面板的数据类型。字段与后端 routes/*.py、services/*.py 一一对应，
 * 不改后端、不臆造字段。旧前端散落的 DOM 逻辑只在这里定形状，表现交给组件。
 */
export type WeatherSize = 'sm' | 'md' | 'lg'

export interface WeatherHour {
  time?: string
  temp?: number | null
  pop?: number | null
  code?: number
}

export interface WeatherToday {
  tmax?: number | null
  tmin?: number | null
  sunrise?: string
  sunset?: string
  pop_max?: number | null
}

export interface WeatherData {
  city?: string
  temp?: number | null
  feels?: number | null
  code?: number
  text?: string
  wind?: number | null
  aqi?: number | null
  humidity?: number | null
  is_day?: number
  hourly?: WeatherHour[]
  today?: WeatherToday
  updated?: string
  stale?: boolean
  unavailable?: boolean
}

export interface SceneItem {
  scene_id: string
  name: string
  home_id: string
  owner_uid?: number
}

export interface AutoEntry {
  device?: string
  name?: string
  key?: string
  value?: unknown
}

export interface AutoCounts {
  trigger: number
  condition: number
  action: number
  else?: number
}

export interface AutomationItem {
  scene_id: string
  name: string
  home_id?: string
  home_name?: string
  enable: boolean
  summary?: string
  counts: AutoCounts
  update_time?: string
  triggers?: AutoEntry[]
  conditions?: AutoEntry[]
  actions?: AutoEntry[]
  else_actions?: AutoEntry[]
}

export interface AutomationDetail extends AutomationItem {
  raw?: unknown
}

export type AutomationPatch = { name?: string; enable?: boolean }

export interface EventItem {
  ts?: number
  time?: string
  type?: string
  did?: string
  name?: string
  text?: string
}

/** 米家消息中心的一条未读消息（后端已归一化）。 */
export interface NoticeItem {
  msg_id: number
  ts: number
  time: string
  kind: number
  title: string
  body: string
  did: string
  model: string
  home: string
  room: string
  event: string
  seen: number
}

export interface ApiResult {
  ok: boolean
  error?: string
  sent?: boolean
  result?: unknown
  preview?: unknown
  created_id?: string | number
  [key: string]: unknown
}
