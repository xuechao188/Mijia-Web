/* 其余面板数据层（Vue 版）：场景 / 自动化 / 事件流 / 天气。
 *
 * 与 static/app.js 的 loadScenes / loadAutomations / loadEvents / loadWeather
 * 一一对应，端点与轮询节奏都不改后端，也不改 ④⑤ 已验收的 stores。
 * 三条写入链路沿用旧版守卫：每个写请求都显式带 confirm=true；删除还要
 * 名称完全一致；二次确认弹窗在组件层，store 再做一次名称校验兜底。
 */
import { computed, ref } from 'vue'
import { defineStore } from 'pinia'
import { useDevicesStore } from './devices'
import { SIZES, WEATHER_FALLBACK } from '../panels/weather'
import { runPayload, runToast } from '../panels/scenes'
import { deleteNameMatch } from '../panels/automations'
import type { CreateForm } from '../panels/automations'
import type {
  ApiResult, AutomationDetail, AutomationItem, AutomationPatch,
  EventItem, SceneItem, WeatherData, WeatherSize,
} from '../panels/types'

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

export const EVENTS_POLL_MS = 15000
export const SCENES_POLL_MS = 300000
export const AUTOS_POLL_MS = 300000
export const WEATHER_POLL_MS = 600000

export const usePanelsStore = defineStore('panels', () => {
  /* ---------------- 场景 ---------------- */
  /* scenes 永远是云端返回的全部条目；界面只渲染 scopedScenes（当前家庭那批）。
   * 场景是家庭级的：与自动化同源，按 home_id 过滤，切家庭后只显示该家庭场景。 */
  const scenes = ref<SceneItem[]>([])
  const sceneBusy = ref<Record<string, boolean>>({})

  /** 当前家庭（顶部家庭切换器选中的那个），与自动化共用 activeHome。 */
  const sceneHome = computed(() => devices.activeHome)
  /** 只留当前家庭的场景。设备树还没回来时先给全量，避免闪一下「0 个」。
   *  场景条目只有 home_id，所以一律按 id 比对（与自动化同规则）。 */
  const scopedScenes = computed<SceneItem[]>(() => {
    const h = sceneHome.value
    if (!h) return scenes.value
    const hid = String(h.id || '')
    if (!hid) return scenes.value
    return scenes.value.filter((s) => String(s.home_id || '') === hid)
  })
  const sceneCount = computed(() => scopedScenes.value.length)

  /* ---------------- 自动化 ---------------- */
  /* automations 永远是云端返回的全部条目；界面只渲染 scopedAutomations
   * （当前家庭那批）。自动化是家庭级的：信地的 19 条不会出现在西山银杏下面。 */
  const automations = ref<AutomationItem[]>([])
  const autoWritable = ref(false)
  const autoCreateSupported = ref(false)
  const autoDeleteSupported = ref(false)
  const autoHomes = ref<string[]>([])
  const autoCreateOpen = ref(false)
  const autoDetail = ref<AutomationDetail | null>(null)
  const autoDetailId = ref<string | null>(null)
  const autoDrawerOpen = ref(false)
  const autoBusy = ref(false)

  /** 当前家庭（顶部家庭切换器选中的那个）。 */
  const autoHome = computed(() => devices.activeHome)
  const autoHomeName = computed(() => (autoHome.value ? autoHome.value.name : ''))
  /** 只留当前家庭的自动化。设备树还没回来时先给全量，避免闪一下「0 条」。
   *  两边都有 home_id 时只认 id：同名家庭（重建过一次）不能靠名字串门。 */
  const scopedAutomations = computed<AutomationItem[]>(() => {
    const h = autoHome.value
    if (!h) return automations.value
    const hid = String(h.id || '')
    const hname = h.name
    return automations.value.filter((a) => {
      const aid = String(a.home_id || '')
      if (hid && aid) return aid === hid
      return a.home_name === hname
    })
  })
  const autoCount = computed(() => scopedAutomations.value.length)
  const autoEnabled = computed(() => scopedAutomations.value.filter((a) => a.enable).length)

  /* ---------------- 事件流 ---------------- */
  const events = ref<EventItem[]>([])
  const eventSummary = ref<Record<string, number>>({})

  /* ---------------- 天气 ---------------- */
  const weather = ref<WeatherData | null>(null)
  const weatherCity = ref(localStorage.getItem('mi-weather-city') || '')
  const weatherSize = ref<WeatherSize>(
    (SIZES as string[]).includes(localStorage.getItem('mi-weather-size') || '')
      ? (localStorage.getItem('mi-weather-size') as WeatherSize)
      : 'md',
  )
  const weatherDrawerOpen = ref(false)

  const devices = useDevicesStore()
  let timers: Array<ReturnType<typeof setInterval>> = []

  function toast(msg: string): void { devices.toast(msg) }

  /* ---------------- 三种抽屉互斥 ---------------- */
  function closeOtherDrawers(): void {
    devices.closeDrawer()
    autoDrawerOpen.value = false
    autoDetailId.value = null
    autoDetail.value = null
    weatherDrawerOpen.value = false
  }
  function closeAllDrawers(): void { closeOtherDrawers() }
  /** 设备抽屉打开时只收起面板抽屉，不能反过来把刚打开的设备抽屉关掉。 */
  function closePanelDrawers(): void {
    autoDrawerOpen.value = false
    autoDetailId.value = null
    autoDetail.value = null
    weatherDrawerOpen.value = false
  }

  /* ---------------- 场景 ---------------- */
  async function loadScenes(): Promise<void> {
    try {
      const r = await apiGet<{ ok: boolean; scenes?: SceneItem[] }>('/api/scenes')
      scenes.value = [...(r.scenes || [])]
    } catch { /* 场景失败不打扰主流程，沿用旧版 */ }
  }

  /** 返回是否真的执行成功——界面只在成功时给砖块「收到」的反馈。 */
  async function runScene(s: SceneItem): Promise<boolean> {
    if (sceneBusy.value[s.scene_id]) return false
    sceneBusy.value = { ...sceneBusy.value, [s.scene_id]: true }
    let ok = false
    try {
      const r = await apiPost<ApiResult>('/api/scenes/run', runPayload(s))
      ok = Boolean(r.ok)
      toast(runToast(r, s))
    } catch {
      toast('场景执行失败')
    } finally {
      const m = { ...sceneBusy.value }
      delete m[s.scene_id]
      sceneBusy.value = m
      void loadEvents()   // 后端会记一条 scene 事件
    }
    return ok
  }

  /* ---------------- 自动化 ---------------- */
  async function loadAutomations(force = false): Promise<void> {
    try {
      const r = await apiGet<{
        ok: boolean; automations?: AutomationItem[]; homes?: string[]
        count?: number; enabled?: number; writable?: boolean
        create_supported?: boolean; delete_supported?: boolean
      }>('/api/automations' + (force ? '?force=1' : ''))
      if (!r.ok) return
      automations.value = [...(r.automations || [])]
      autoHomes.value = [...(r.homes || [])]
      autoWritable.value = Boolean(r.writable)
      autoCreateSupported.value = Boolean(r.create_supported)
      autoDeleteSupported.value = Boolean(r.delete_supported)
    } catch { /* 自动化读取失败不打扰主流程 */ }
  }

  /* 面板不再折叠：新建表单直接就地展开/收起。 */
  function toggleAutoCreate(): void {
    autoCreateOpen.value = !autoCreateOpen.value
  }

  async function openAutoDetail(sceneId: string): Promise<void> {
    closeOtherDrawers()
    autoDrawerOpen.value = true
    autoDetailId.value = sceneId
    autoDetail.value = null
    try {
      const r = await apiGet<{ ok: boolean; item?: AutomationDetail }>(
        '/api/automations/detail?scene_id=' + encodeURIComponent(sceneId))
      // 抽屉可能已被切走，落后的响应不能覆盖当前内容
      if (autoDrawerOpen.value && autoDetailId.value === sceneId) {
        autoDetail.value = r.ok ? (r.item || null) : null
      }
    } catch {
      if (autoDrawerOpen.value && autoDetailId.value === sceneId) autoDetail.value = null
    }
  }

  function closeAutoDetail(): void {
    autoDrawerOpen.value = false
    autoDetailId.value = null
    autoDetail.value = null
  }

  async function previewEdit(sceneId: string, patch: AutomationPatch): Promise<ApiResult> {
    try {
      return await apiPost<ApiResult>('/api/automations/preview', { scene_id: sceneId, patch })
    } catch (e) {
      return { ok: false, error: String(e) }
    }
  }

  async function applyEdit(item: AutomationItem, patch: AutomationPatch): Promise<ApiResult> {
    autoBusy.value = true
    try {
      const r = await apiPost<ApiResult>('/api/automations/apply', {
        scene_id: item.scene_id, patch, confirm: true,
      })
      toast(r.ok ? '自动化已更新' : '自动化写入失败')
      if (r.ok) {
        await loadAutomations(true)
        if (autoDrawerOpen.value && autoDetailId.value === item.scene_id) {
          await openAutoDetail(item.scene_id)
        }
      }
      return r
    } catch (e) {
      toast('自动化写入失败')
      return { ok: false, error: String(e) }
    } finally {
      autoBusy.value = false
    }
  }

  async function previewCreate(p: CreateForm): Promise<ApiResult> {
    try {
      return await apiPost<ApiResult>('/api/automations/create/preview', p)
    } catch (e) {
      return { ok: false, error: String(e) }
    }
  }

  async function createAutomation(p: CreateForm): Promise<ApiResult> {
    autoBusy.value = true
    try {
      const r = await apiPost<ApiResult>('/api/automations/create', { ...p, confirm: true })
      toast(r.ok ? '自动化已创建' : '自动化创建失败')
      if (r.ok) await loadAutomations(true)
      return r
    } catch (e) {
      toast('自动化创建失败')
      return { ok: false, error: String(e) }
    } finally {
      autoBusy.value = false
    }
  }

  async function previewDelete(sceneId: string, name: string): Promise<ApiResult> {
    try {
      return await apiPost<ApiResult>('/api/automations/delete/preview', { scene_id: sceneId, name })
    } catch (e) {
      return { ok: false, error: String(e) }
    }
  }

  async function deleteAutomation(item: AutomationItem, name: string): Promise<ApiResult> {
    if (!deleteNameMatch(name, item)) {
      toast('名称复核不一致，请完整输入自动化名称')
      return { ok: false, error: '名称复核不一致' }
    }
    autoBusy.value = true
    try {
      const r = await apiPost<ApiResult>('/api/automations/delete', {
        scene_id: item.scene_id, name, confirm: true,
      })
      if (r.ok) {
        toast('自动化已删除')
        closeAutoDetail()
        await loadAutomations(true)
      } else {
        toast('自动化删除失败')
      }
      return r
    } catch (e) {
      toast('自动化删除失败')
      return { ok: false, error: String(e) }
    } finally {
      autoBusy.value = false
    }
  }

  /* ---------------- 事件流 ---------------- */
  async function loadEvents(): Promise<void> {
    try {
      const r = await apiGet<{
        ok: boolean; events?: EventItem[]; summary?: Record<string, number>
      }>('/api/events')
      events.value = [...(r.events || [])]
      eventSummary.value = { ...(r.summary || {}) }
    } catch { /* ignore，沿用旧版 */ }
  }

  /* ---------------- 天气 ---------------- */
  async function loadWeather(): Promise<void> {
    try {
      const q = weatherCity.value ? '?city=' + encodeURIComponent(weatherCity.value) : ''
      const r = await apiGet<{ ok: boolean; weather?: WeatherData | null }>('/api/weather' + q)
      weather.value = (r && r.weather) || weather.value || { ...WEATHER_FALLBACK }
    } catch {
      weather.value = weather.value || { ...WEATHER_FALLBACK }
    }
  }

  function setWeatherSize(size: WeatherSize): void {
    if (!(SIZES as string[]).includes(size)) return
    weatherSize.value = size
    localStorage.setItem('mi-weather-size', size)
  }

  async function setWeatherCity(city: string): Promise<void> {
    weatherCity.value = city || ''
    if (city) localStorage.setItem('mi-weather-city', city)
    else localStorage.removeItem('mi-weather-city')
    toast(city ? '天气城市已切换为 ' + city : '已恢复默认城市')
    await loadWeather()
  }

  function openWeatherDrawer(): void {
    closeOtherDrawers()
    weatherDrawerOpen.value = true
  }
  function closeWeatherDrawer(): void { weatherDrawerOpen.value = false }

  /* ---------------- 生命周期 ---------------- */
  async function bootstrap(): Promise<void> {
    await Promise.all([
      loadScenes(), loadAutomations(), loadEvents(), loadWeather(),
    ])
  }

  function startPolling(): void {
    stopPolling()
    timers = [
      setInterval(() => void loadEvents(), EVENTS_POLL_MS),
      setInterval(() => void loadScenes(), SCENES_POLL_MS),
      setInterval(() => void loadAutomations(), AUTOS_POLL_MS),
      setInterval(() => void loadWeather(), WEATHER_POLL_MS),
    ]
  }
  function stopPolling(): void {
    for (const t of timers) clearInterval(t)
    timers = []
  }

  return {
    scenes, sceneBusy, scopedScenes, sceneCount,
    automations, autoCount, autoEnabled, autoWritable,
    scopedAutomations, autoHome, autoHomeName,
    autoCreateSupported, autoDeleteSupported, autoHomes, autoCreateOpen,
    autoDetail, autoDetailId, autoDrawerOpen, autoBusy,
    events, eventSummary, weather, weatherCity, weatherSize, weatherDrawerOpen,
    toast, closeOtherDrawers, closeAllDrawers, closePanelDrawers,
    loadScenes, runScene, loadAutomations, toggleAutoCreate,
    openAutoDetail, closeAutoDetail, previewEdit, applyEdit, previewCreate,
    createAutomation, previewDelete, deleteAutomation,
    loadEvents, loadWeather, setWeatherSize, setWeatherCity,
    openWeatherDrawer, closeWeatherDrawer,
    bootstrap, startPolling, stopPolling,
  }
})
