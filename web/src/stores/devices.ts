/* 设备数据层（Vue 版）。
 *
 * 与 static/app.js 一一对应：/api/devices、/api/live（3s 快轮询 / 45s 全量）、
 * /api/layout、/api/groups、/api/history、/api/switch、/api/set 都不改后端。
 * 保留三个旧界面踩过坑才定下的规则：
 *   1) 版本竞态：用户操作递增 ver[did]，落后的轮询结果直接丢弃；
 *   2) 乐观更新：开关先本地翻转，失败再回滚并提示；
 *   3) 快轮询只合并 on/onN，不能冲掉读数与曲线。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import * as groupLogic from '../devices/groups'
import {
  STAT_FILTER_ONLINE, applyOrder, cardHasContent, filterByStat, statCounts,
  statGroups, visibleDevices,
} from '../devices/content'
import type {
  DeviceControl, DeviceGroup, DeviceView, IrCmd, LayoutState, LiveState,
  SeriesMap, Size,
} from '../devices/types'

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path)
  return (await r.json()) as T
}
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return (await r.json()) as T
}
function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

export const QUICK_POLL_MS = 3000
export const FULL_POLL_MS = 45000
export const HISTORY_HOURS = 6

export const useDevicesStore = defineStore('devices', () => {
  const devices = ref<Record<string, DeviceView>>({})
  const live = ref<Record<string, LiveState>>({})
  const ver = ref<Record<string, number>>({})
  const groups = ref<DeviceGroup[]>([])
  const layout = ref<LayoutState>({ sizes: {}, order: [] })
  const names = ref<Record<string, string>>(readJson('mi-names', {}))
  const metrics = ref<Record<string, string[]>>(readJson('mi-metrics', {}))
  const history = ref<SeriesMap>({})
  /* 该设备的历史取样是否已回来过（空数据也算回来） */
  const historyReady = ref<Record<string, boolean>>({})
  const filter = ref('all')
  const home = ref(localStorage.getItem('mi-home') || '')
  const kw = ref('')
  /* 统计条点出来的第二维筛选：'' 全部 / 'online' 只看在线 / 类型分组 key。
   * 与 filter（家庭·房间·分组）叠加，不写进 URL 也不持久化——刷新回全部。 */
  const statFilter = ref('')
  const drawerDid = ref<string | null>(null)
  const drawerHours = ref(24)
  const holdDid = ref<string | null>(null)
  const mainTab = ref(localStorage.getItem('mi-main-tab') || 'devices')
  const toastMsg = ref('')
  const loading = ref(false)
  const ready = ref(false)
  const syncing = ref(false)

  const deviceList = computed<DeviceView[]>(() => Object.values(devices.value))
  const tree = computed(() => groupLogic.buildTree(deviceList.value))
  const navNodes = computed(() => groupLogic.nodes(tree.value, groups.value))
  /* 米家的层级是「先选家庭，再看房间」：顶部只切家庭，侧栏只列该家庭的房间。
   * 家庭来自 /api/devices 的 home 字段，选中项记在本机，下次进来还是这个家。 */
  const homes = computed(() => tree.value.homes)
  const activeHome = computed(() =>
    homes.value.find((h) => h.name === home.value) || homes.value[0] || null)
  const roomNav = computed<groupLogic.NavNode[]>(() =>
    groupLogic.roomNodes(tree.value, activeHome.value ? activeHome.value.name : ''))
  /* scoped = 当前家庭 / 房间 / 搜索的范围（统计条的读数口径） */
  const scoped = computed(() => visibleDevices(
    deviceList.value, filter.value, groups.value, kw.value, layout.value, names.value,
  ))
  /* visible = 范围 + 统计条筛选（网格真正渲染的卡片） */
  const visible = computed(() => filterByStat(scoped.value, statFilter.value))
  const homesCount = computed(() => new Set(visible.value.map((d) => d.home).filter(Boolean)).size)
  /* 统计条只读「当前范围」：顶部选了家庭、侧栏选了房间、搜索了关键词之后，
   * 读数跟着筛过的设备走，不再把全屋 96 台当成这个房间的家底。 */
  const stats = computed(() => statCounts(scoped.value, live.value))
  const typeStats = computed(() => statGroups(scoped.value, live.value))
  /* 筛选标签：'online' 说成「在线」，类型组用格子里那个词 */
  const statFilterLabel = computed(() => {
    if (!statFilter.value) return ''
    if (statFilter.value === STAT_FILTER_ONLINE) return '在线'
    return typeStats.value.find((g) => g.key === statFilter.value)?.label || ''
  })
  const drawerDevice = computed(() => drawerDid.value ? devices.value[drawerDid.value] || null : null)
  const filterLabel = computed(() => groupLogic.label(filter.value, tree.value, groups.value))

  let toastTimer: ReturnType<typeof setTimeout> | null = null
  let quickTimer: ReturnType<typeof setInterval> | null = null
  let fullTimer: ReturnType<typeof setInterval> | null = null
  let quickBusy = false
  let fullBusy = false

  function toast(msg: string): void {
    toastMsg.value = msg
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => { toastMsg.value = '' }, 2600)
  }

  function bump(did: string): void {
    ver.value[did] = (ver.value[did] || 0) + 1
  }

  function displayName(d: DeviceView): string {
    return names.value[String(d.did)] || d.name
  }

  function setName(did: string, name: string): void {
    const m = { ...names.value }
    const clean = name.trim()
    if (clean && clean !== devices.value[did]?.name) m[did] = clean
    else delete m[did]
    names.value = m
    localStorage.setItem('mi-names', JSON.stringify(m))
  }

  function setMetrics(did: string, keys: string[]): void {
    const m = { ...metrics.value }
    if (keys.length) m[did] = keys.slice(0, 2)
    else delete m[did]
    metrics.value = m
    localStorage.setItem('mi-metrics', JSON.stringify(m))
  }

  function toggleMetric(did: string, key: string): void {
    let cur = (metrics.value[did] || []).slice()
    if (cur.includes(key)) cur = cur.filter((x) => x !== key)
    else cur = [...cur, key].slice(-2)
    setMetrics(did, cur)
  }

  function setMainTab(tab: string): void {
    mainTab.value = tab
    localStorage.setItem('mi-main-tab', tab)
  }

  /** 切家庭：视图直接落到该家庭的「全部设备」，房间列表随之重算。
   *  换范围时统计筛选一起归零：留着上一处的「只看照明」，进到没灯具的房间
   *  只会看到一屏空白，还以为设备丢了。 */
  function setHome(name: string): void {
    home.value = name
    localStorage.setItem('mi-home', name)
    filter.value = groupLogic.key('home', name)
    statFilter.value = ''
  }

  /** 选中房间时把家庭一起校准，避免「家庭 = A、房间 ∈ B」的错位状态。
   *  'all' 不再是一个全局视图（家庭由顶部决定），直接落到当前家庭的全部设备。 */
  function setFilter(k: string): void {
    const next = validFilter(k)
    filter.value = next
    statFilter.value = ''
    const f = groupLogic.parseKey(next)
    if (f.type === 'home' || f.type === 'room') {
      home.value = f.a
      localStorage.setItem('mi-home', f.a)
    }
  }

  /** 再点一次同一个口子就取消，不用去找「清除」——这是计数条的常规手感。 */
  function toggleStatFilter(k: string): void {
    statFilter.value = statFilter.value === k ? '' : k
  }
  function clearStatFilter(): void {
    statFilter.value = ''
  }

  /** 过滤键失效（分组被删、设备换了家庭）时回落到当前家庭的「全部设备」。 */
  function validFilter(k: string): string {
    const h = activeHome.value
    const fallback = h ? groupLogic.key('home', h.name) : 'all'
    if (k === 'all') return fallback
    return navNodes.value.some((n) => n.key === k) ? k : fallback
  }

  /* ---------------- 拉取 ---------------- */
  async function loadDevices(): Promise<void> {
    const r = await apiGet<{ ok: boolean; devices?: DeviceView[]; logged_in?: boolean }>('/api/devices')
    const map: Record<string, DeviceView> = {}
    for (const d of r.devices || []) map[String(d.did)] = d
    devices.value = map
    filter.value = validFilter(filter.value)
    syncing.value = Boolean(r.logged_in) && deviceList.value.length === 0
    ready.value = true
  }

  async function loadLayout(): Promise<void> {
    try {
      const r = await apiGet<{ ok: boolean; sizes?: Record<string, Size>; order?: string[] }>('/api/layout')
      if (r.ok) layout.value = { sizes: r.sizes || {}, order: r.order || [] }
    } catch { /* 离线/失败不影响其它功能 */ }
  }

  async function loadGroups(): Promise<void> {
    try {
      const r = await apiGet<{ groups?: DeviceGroup[] }>('/api/groups')
      groups.value = r.groups || []
    } catch { groups.value = [] }
  }

  async function postGroups(payload: Record<string, unknown>): Promise<boolean> {
    try {
      const r = await apiPost<{ ok: boolean; error?: string; groups?: DeviceGroup[] }>('/api/groups', payload)
      if (!r.ok) { toast(r.error || '分组操作失败'); return false }
      groups.value = r.groups || []
      filter.value = validFilter(filter.value)
      return true
    } catch { toast('网络异常，分组未保存'); return false }
  }

  async function mergeLiveData(data: Record<string, LiveState>, snap: Record<string, number>, quick: boolean): Promise<void> {
    for (const [did, cur] of Object.entries(data || {})) {
      if ((ver.value[did] || 0) !== (snap[did] || 0)) continue // 刚被用户操作，丢弃
      const bucket = { ...(live.value[did] || {}) }
      if (quick) {
        for (const k in cur) if (k === 'on' || /^on\d+$/.test(k)) bucket[k] = cur[k]
      } else {
        Object.assign(bucket, cur)
      }
      live.value[did] = bucket
    }
  }

  async function pollQuick(): Promise<void> {
    if (quickBusy) return
    quickBusy = true
    try {
      const snap = { ...ver.value }
      const r = await apiGet<{ ok: boolean; live?: Record<string, LiveState> }>('/api/live?quick=1')
      if (r.ok) await mergeLiveData(r.live || {}, snap, true)
    } catch { /* 后端短暂不可达，下一轮再说 */ }
    quickBusy = false
  }

  async function pollFull(): Promise<void> {
    if (fullBusy) return
    fullBusy = true
    try {
      const snap = { ...ver.value }
      const r = await apiGet<{ ok: boolean; live?: Record<string, LiveState> }>('/api/live')
      if (r.ok) await mergeLiveData(r.live || {}, snap, false)
      await loadHistory()
    } catch { /* ignore */ }
    fullBusy = false
  }

  async function loadHistory(): Promise<void> {
    try {
      const r = await apiGet<{ ok: boolean; series?: SeriesMap }>(
        `/api/history?hours=${HISTORY_HOURS}&points=72`,
      )
      if (!r.ok) return
      const merged: SeriesMap = { ...history.value }
      for (const [did, keys] of Object.entries(r.series || {})) {
        merged[did] = { ...(merged[did] || {}), ...keys }
      }
      history.value = merged
    } catch { /* ignore */ }
  }

  async function loadDrawerHistory(did: string): Promise<void> {
    try {
      const r = await apiGet<{ ok: boolean; series?: SeriesMap }>(
        `/api/history?did=${encodeURIComponent(did)}&hours=${drawerHours.value}&points=96`,
      )
      if (drawerDid.value !== did) return
      if (r.ok) {
        const cur = (r.series || {})[String(did)] || {}
        history.value = { ...history.value, [did]: { ...(history.value[did] || {}), ...cur } }
      }
    } catch { /* ignore */ }
    /* 有数据没数据都记一笔：详情面板要区分「还没拉到」与「确实没有」，
       前者不能当成没数据把历史趋势整块拿掉 */
    historyReady.value = { ...historyReady.value, [did]: true }
  }

  async function bootstrap(): Promise<void> {
    loading.value = true
    await Promise.all([loadDevices(), loadLayout(), loadGroups(), pollFull(), loadHistory()])
    loading.value = false
    // 红外按键表在云端：不阻塞首屏，拿到后卡片上的按键自己会出现
    void ensureIrKeys()
  }

  async function refresh(): Promise<void> {
    toast('刷新中…')
    loading.value = true
    try {
      const r = await apiPost<{ ok: boolean; devices?: DeviceView[] }>('/api/devices/refresh', {})
      const map: Record<string, DeviceView> = {}
      for (const d of r.devices || []) map[String(d.did)] = d
      devices.value = map
      await pollFull()
      toast('设备列表已刷新')
    } catch { toast('刷新失败，请稍后重试') }
    loading.value = false
  }

  /* ---------------- 控制 ---------------- */
  function applyOptimistic(did: string, patch: LiveState): void {
    live.value[did] = { ...(live.value[did] || {}), ...patch }
  }

  async function toggle(did: string, on: boolean, key = 'on'): Promise<void> {
    const d = devices.value[did]
    if (d && d.online === false) { toast('设备离线，无法控制'); return }
    bump(did)
    applyOptimistic(did, { [key]: on })
    if (key === 'on1' || key === 'on') applyOptimistic(did, { on })
    try {
      const r = await apiPost<{ ok: boolean; error?: string; hint?: string }>(
        '/api/switch', { did, on, key },
      )
      if (!r.ok) {
        bump(did)
        applyOptimistic(did, { [key]: !on })
        toast(r.hint || r.error || '操作失败')
      }
    } catch {
      bump(did)
      applyOptimistic(did, { [key]: !on })
      toast('网络异常，已回滚')
    }
  }

  async function setControl(did: string, c: DeviceControl, value: unknown): Promise<boolean> {
    const d = devices.value[did]
    if (d && d.online === false) { toast('设备离线，无法控制'); return false }
    bump(did)
    applyOptimistic(did, { [c.key]: value })
    try {
      const r = await apiPost<{ ok: boolean; error?: string; hint?: string }>(
        '/api/set', { did, siid: c.siid, piid: c.piid, value },
      )
      if (!r.ok) {
        bump(did)
        toast(r.hint || r.error || '设置失败')
        return false
      }
      return true
    } catch {
      bump(did)
      toast('网络异常')
      return false
    }
  }

  /** 单台设备回读全量读数。
   *  灯具切「模式」时云端会连带改亮度和色温，写成功后再读一次才能让滑块
   *  与状态区显示真实值（乐观更新只知道模式变了，不知道亮度被推到多少）。 */
  async function refreshDevice(did: string): Promise<void> {
    const snap = { ...ver.value }
    try {
      const r = await apiGet<{ ok: boolean; live?: Record<string, LiveState> }>(
        `/api/live?did=${encodeURIComponent(did)}`,
      )
      if (r.ok && r.live) await mergeLiveData(r.live, snap, false)
    } catch { /* 读失败就沿用乐观值，不打扰用户 */ }
  }

  /** 写完之后的两拍回读：设备先把模式落地，再更新联动属性，一次不够。 */
  async function settleDevice(did: string): Promise<void> {
    await new Promise((r) => setTimeout(r, 600))
    await refreshDevice(did)
    await new Promise((r) => setTimeout(r, 1600))
    await refreshDevice(did)
  }

  /* ---------------- 红外遥控 ----------------
   * 红外是单向发码：没有回读状态，所以这里不做乐观更新、不写 live，
   * 只把「发出去了没有」告诉用户。按键表在云端，首次渲染可能还没到，
   * 因此打开详情或刚启动时按 did 补拉一次。 */
  async function pressIrKey(did: string, keyId: unknown, label = ''): Promise<boolean> {
    if (keyId === undefined || keyId === null) return false
    const d = devices.value[did]
    if (d && d.online === false) { toast('设备离线，指令发不出去'); return false }
    try {
      const r = await apiPost<{ ok: boolean; error?: string; hint?: string }>(
        '/api/ir/press', { did, key_id: keyId },
      )
      if (!r.ok) { toast(r.hint || r.error || '发送失败'); return false }
      toast('已发送：' + (label || '按键'))
      return true
    } catch { toast('网络异常，指令未发出'); return false }
  }

  async function pressIr(did: string, cmd: IrCmd): Promise<boolean> {
    if (cmd.kind === 'key') return pressIrKey(did, cmd.key_id, cmd.label)
    const d = devices.value[did]
    if (d && d.online === false) { toast('设备离线，指令发不出去'); return false }
    try {
      const r = await apiPost<{ ok: boolean; error?: string; hint?: string; label?: string }>(
        '/api/ir/cmd', { did, cmd_id: cmd.id },
      )
      if (!r.ok) { toast(r.hint || r.error || '发送失败'); return false }
      toast('已发送：' + (r.label || cmd.label))
      return true
    } catch { toast('网络异常，指令未发出'); return false }
  }

  /** 设定温度：只发绝对值，不写 live——云端只写不读，写进去就是伪造状态。
   *  界面上的当前温度由面板本地记（localStorage），表示"最后一次发送"。 */
  async function setIrTemp(did: string, value: number): Promise<boolean> {
    const d = devices.value[did]
    if (d && d.online === false) { toast('设备离线，指令发不出去'); return false }
    try {
      const r = await apiPost<{ ok: boolean; error?: string; hint?: string; label?: string }>(
        '/api/ir/temp', { did, value },
      )
      if (!r.ok) { toast(r.hint || r.error || '发送失败'); return false }
      toast('已发送：' + (r.label || value + '°C'))
      return true
    } catch { toast('网络异常，指令未发出'); return false }
  }

  /** 补齐缺失的红外按键表（云端拿，后端有 6 小时缓存）。 */
  async function ensureIrKeys(): Promise<void> {
    const ids = Object.values(devices.value)
      .filter((d) => d.ir && !((d.ir.keys || []).length))
      .map((d) => String(d.did))
      .slice(0, 12)
    for (const did of ids) {
      try {
        const r = await apiGet<{ ok: boolean; keys?: Array<{ id: number | string; name: string }> }>(
          '/api/ir/keys?did=' + encodeURIComponent(did),
        )
        const cur = devices.value[did]
        if (!r.ok || !r.keys || !cur || !cur.ir) continue
        devices.value = { ...devices.value, [did]: { ...cur, ir: { ...cur.ir, keys: r.keys } } }
      } catch { /* 拉不到就保持空，打开详情时会再试一次 */ }
    }
  }

  /* ---------------- 布局与抽屉 ---------------- */
  async function setSize(did: string, size: Size): Promise<void> {
    layout.value = { ...layout.value, sizes: { ...layout.value.sizes, [did]: size } }
    try { await apiPost('/api/layout/size', { did, size }) } catch { /* 静默 */ }
  }

  async function saveOrder(order: string[]): Promise<void> {
    layout.value = { ...layout.value, order }
    try { await apiPost('/api/layout/order', { order }) } catch { /* 静默 */ }
  }

  function orderedDids(): string[] {
    return applyOrder(deviceList.value, layout.value.order).map((d) => String(d.did))
  }

  function openDrawer(did: string): void {
    drawerDid.value = did
    historyReady.value = { ...historyReady.value, [did]: false }
    void loadDrawerHistory(did)
    // 红外遥控：抽屉里要铺满按键，缺的先补一次
    const d = devices.value[did]
    if (d && d.ir && !((d.ir.keys || []).length)) void ensureIrKeys()
  }
  function closeDrawer(): void { drawerDid.value = null }
  function setDrawerHours(h: number): void {
    drawerHours.value = h
    if (drawerDid.value) void loadDrawerHistory(drawerDid.value)
  }
  function setHold(did: string, on: boolean): void {
    if (on) holdDid.value = did
    else if (holdDid.value === did) holdDid.value = null
  }

  function startPolling(): void {
    stopPolling()
    quickTimer = setInterval(() => { void pollQuick() }, QUICK_POLL_MS)
    fullTimer = setInterval(() => { void pollFull() }, FULL_POLL_MS)
  }
  function stopPolling(): void {
    if (quickTimer) clearInterval(quickTimer)
    if (fullTimer) clearInterval(fullTimer)
    quickTimer = null
    fullTimer = null
  }

  return {
    devices, live, ver, groups, layout, names, metrics, history, historyReady,
    filter, home, kw,
    drawerDid, drawerHours, holdDid, mainTab, toastMsg, loading, ready, syncing,
    deviceList, tree, navNodes, homes, activeHome, roomNav,
    visible, homesCount, stats, typeStats, statFilter, statFilterLabel,
    drawerDevice, filterLabel,
    toast, displayName, setName, setMetrics, toggleMetric, setMainTab, setHome, setFilter,
    toggleStatFilter, clearStatFilter,
    loadDevices, loadLayout, loadGroups, postGroups, pollQuick, pollFull,
    loadHistory, loadDrawerHistory, bootstrap, refresh,
    toggle, setControl, refreshDevice, settleDevice, setSize, saveOrder, orderedDids,
    pressIr, pressIrKey, setIrTemp, ensureIrKeys,
    openDrawer, closeDrawer, setDrawerHours, setHold,
    startPolling, stopPolling, cardHasContent,
  }
})
