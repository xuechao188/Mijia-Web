/* 家庭 / 房间两级分组与自定义分组的筛选逻辑（Vue 版）。
 *
 * 与 static/groups.js 同源：家庭与房间来自 /api/devices 的 home/room 字段，
 * 自定义分组来自 /api/groups（本机持久化，可跨家庭组合设备）。
 * 无 DOM 依赖，Node 可直接加载做交叉校验。
 */
import type { DeviceGroup, DeviceView } from './types'

// 分组名里几乎不可能出现的分隔符，避免 "信地:客厅" 这类 key 冲突
const SEP = '\u0001'

export interface HomeNode {
  name: string
  id: string
  dids: string[]
  rooms: RoomNode[]
}
export interface RoomNode {
  name: string
  id: string
  dids: string[]
}
export interface Tree {
  homes: HomeNode[]
  unassigned: string[]
}
export interface NavNode {
  key: string
  type: 'all' | 'home' | 'room' | 'unassigned' | 'group'
  label: string
  count: number
  home?: string
  id?: string
}

function byName(a: { name?: string }, b: { name?: string }): number {
  return String(a.name || '').localeCompare(String(b.name || ''), 'zh-CN')
}

export function key(type: string, a?: unknown, b?: unknown): string {
  if (type === 'all') return 'all'
  if (type === 'unassigned') return 'unassigned'
  return [type, a == null ? '' : String(a), b == null ? '' : String(b)].join(SEP)
}

export function parseKey(k: string | null | undefined): { type: string; a: string; b: string } {
  const p = String(k == null ? 'all' : k).split(SEP)
  return { type: p[0] || 'all', a: p[1] || '', b: p[2] || '' }
}

export function buildTree(devices: DeviceView[]): Tree {
  const homeMap: Record<string, {
    name: string; id: string; dids: string[]
    roomMap: Record<string, RoomNode>; roomOrder: string[]
  }> = {}
  const homeOrder: string[] = []
  const unassigned: string[] = []
  for (const d of devices || []) {
    const did = String(d.did)
    const home = String(d.home || '')
    const room = String(d.room || '')
    if (!home) { unassigned.push(did); continue }
    if (!homeMap[home]) {
      homeMap[home] = {
        name: home, id: String(d.home_id || ''), dids: [],
        roomMap: {}, roomOrder: [],
      }
      homeOrder.push(home)
    }
    const h = homeMap[home]
    h.dids.push(did)
    if (!h.roomMap[room]) {
      h.roomMap[room] = { name: room, id: String(d.room_id || ''), dids: [] }
      h.roomOrder.push(room)
    }
    h.roomMap[room].dids.push(did)
  }
  const homes: HomeNode[] = homeOrder.map((name) => {
    const h = homeMap[name]
    return {
      name: h.name, id: h.id, dids: h.dids,
      rooms: h.roomOrder.map((rn) => h.roomMap[rn]).sort(byName),
    }
  }).sort(byName)
  return { homes, unassigned }
}

export function total(tree: Tree): number {
  const t = tree || ({} as Tree)
  let n = (t.unassigned || []).length
  for (const h of t.homes || []) n += (h.dids || []).length
  return n
}

function findHome(tree: Tree, name: string): HomeNode | null {
  const hs = (tree || ({} as Tree)).homes || []
  return hs.find((h) => h.name === name) || null
}
function findRoom(tree: Tree, home: string, room: string): RoomNode | null {
  const h = findHome(tree, home)
  if (!h) return null
  return (h.rooms || []).find((r) => (r.name || '') === room) || null
}
function findGroup(groups: DeviceGroup[], id: string): DeviceGroup | null {
  return (groups || []).find((g) => String(g.id) === String(id)) || null
}

export function nodes(tree: Tree, groups: DeviceGroup[]): NavNode[] {
  const out: NavNode[] = [{ key: key('all'), type: 'all', label: '全部设备', count: total(tree) }]
  for (const h of (tree || ({} as Tree)).homes || []) {
    out.push({ key: key('home', h.name), type: 'home', label: h.name, count: (h.dids || []).length })
    for (const r of h.rooms || []) {
      out.push({
        key: key('room', h.name, r.name), type: 'room',
        label: r.name || '未分房间', home: h.name, count: (r.dids || []).length,
      })
    }
  }
  if (((tree || ({} as Tree)).unassigned || []).length) {
    out.push({ key: key('unassigned'), type: 'unassigned', label: '未分配', count: tree.unassigned.length })
  }
  for (const g of groups || []) {
    out.push({ key: key('group', g.id), type: 'group', label: g.name, id: String(g.id), count: (g.dids || []).length })
  }
  return out
}

/** 单个家庭的房间列表（米家式层级：家庭在顶部选，这里只列房间）。
 *  首项是该家庭的「全部设备」，别的家庭与没有归属家庭的设备都不出现在列表里
 *  —— 后者不属于任何家庭，混在里面会让「全部设备 N + 未分配 1」对不上账。 */
export function roomNodes(tree: Tree, homeName: string): NavNode[] {
  const out: NavNode[] = []
  const h = findHome(tree, homeName)
  if (!h) return out
  out.push({
    key: key('home', h.name), type: 'home',
    label: '全部设备', count: (h.dids || []).length,
  })
  for (const r of h.rooms || []) {
    out.push({
      key: key('room', h.name, r.name), type: 'room',
      label: r.name || '未分房间', home: h.name, count: (r.dids || []).length,
    })
  }
  return out
}

export function matches(k: string, device: DeviceView, groups: DeviceGroup[]): boolean {
  const f = parseKey(k)
  const d = device || ({} as DeviceView)
  if (f.type === 'all') return true
  if (f.type === 'unassigned') return !String(d.home || '')
  if (f.type === 'home') return String(d.home || '') === f.a
  if (f.type === 'room') return String(d.home || '') === f.a && String(d.room || '') === f.b
  if (f.type === 'group') {
    const g = findGroup(groups, f.a)
    return !!g && (g.dids || []).map(String).indexOf(String(d.did)) >= 0
  }
  return true
}

export function count(k: string, tree: Tree, groups: DeviceGroup[]): number {
  const f = parseKey(k)
  if (f.type === 'all') return total(tree)
  if (f.type === 'unassigned') return ((tree || ({} as Tree)).unassigned || []).length
  if (f.type === 'home') {
    const h = findHome(tree, f.a)
    return h ? (h.dids || []).length : 0
  }
  if (f.type === 'room') {
    const r = findRoom(tree, f.a, f.b)
    return r ? (r.dids || []).length : 0
  }
  if (f.type === 'group') {
    const g = findGroup(groups, f.a)
    return g ? (g.dids || []).length : 0
  }
  return 0
}

export function label(k: string, tree: Tree, groups: DeviceGroup[]): string {
  const f = parseKey(k)
  if (f.type === 'all') return '全部设备'
  if (f.type === 'unassigned') return '未分配'
  if (f.type === 'home') return f.a
  if (f.type === 'room') return f.a + ' / ' + (f.b || '未分房间')
  if (f.type === 'group') {
    const g = findGroup(groups, f.a)
    return g ? g.name : '自定义分组'
  }
  return '全部设备'
}
