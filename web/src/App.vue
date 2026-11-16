<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import LoginPage from './components/LoginPage.vue'
import Sidebar from './components/Sidebar.vue'
import HomeSwitcher from './components/HomeSwitcher.vue'
import DeviceGrid from './components/DeviceGrid.vue'
import DeviceDrawer from './components/DeviceDrawer.vue'
import ScenesPanel from './components/ScenesPanel.vue'
import AutomationsPanel from './components/AutomationsPanel.vue'
import AutomationDrawer from './components/AutomationDrawer.vue'
import EventsPanel from './components/EventsPanel.vue'
import NoticesPanel from './components/NoticesPanel.vue'
import NoticeToasts from './components/NoticeToasts.vue'
import WeatherDrawer from './components/WeatherDrawer.vue'
import ThemePanel from './components/ThemePanel.vue'
import AboutDialog from './components/AboutDialog.vue'
import { useThemeStore } from './stores/theme'
import { useAuthStore } from './stores/auth'
import { useDevicesStore } from './stores/devices'
import { usePanelsStore } from './stores/panels'
import { useNoticesStore } from './stores/notices'
import { breathe, drawerEnter, drawerLeave, pageEnter, pageLeave, themeSweep } from './motion'

type Ping = { ok: boolean; version: string; logged_in: boolean }

const pingText = ref('正在连接后端…')
const appVersion = ref('')
const online = ref(false)
/* 外观面板挂在顶栏右侧的动作组里，点按钮外的任何地方或按 Esc 都收起 */
const themeOpen = ref(false)
/* 关于应用弹窗：点顶栏版本号打开 */
const aboutOpen = ref(false)
const actionsEl = ref<HTMLElement | null>(null)
const pingEl = ref<HTMLElement | null>(null)
/* 通知排在日志前面：设备自己报的事比操作留痕更值得先看 */
const tabNames: Array<[string, string]> = [
  ['devices', '设备'], ['scenes', '场景'], ['automations', '自动化'],
  ['notices', '通知'], ['logs', '日志'],
]

// Store 在这里首次创建，随即把偏好涂到根元素并持久化
const theme = useThemeStore()
const auth = useAuthStore()
const store = useDevicesStore()
const panels = usePanelsStore()
const notices = useNoticesStore()
const tabLabel = computed(() =>
  tabNames.find((t) => t[0] === store.mainTab)?.[1] || '设备')

onMounted(async () => {
  try {
    const res = await fetch('/api/ping')
    const data = (await res.json()) as Ping
    online.value = Boolean(data.ok)
    appVersion.value = data.version || ''
    pingText.value = `后端已连通 · ${data.logged_in ? '已登录' : '未登录'}`
  } catch {
    pingText.value = '后端未连通（主题层仍可独立渲染）'
  }
  await auth.bootstrap()
})
watch(() => auth.phase, (phase) => {
  if (phase === 'app') {
    void store.bootstrap()
    store.startPolling()
    void panels.bootstrap()
    panels.startPolling()
    notices.startPolling()
    // 主壳这时候才挂上，停摆呼吸要等元素出现后再按连通态决定
    void nextTick(() => breathe(pingEl.value, !online.value))
  } else {
    store.stopPolling()
    panels.stopPolling()
    notices.stopPolling()
    store.closeDrawer()
    panels.closeAllDrawers()
  }
})

/* 设备抽屉打开时只收起面板抽屉；反过来由 panels store 的
 * closeOtherDrawers() 负责关设备抽屉，避免两侧互相触发。 */
watch(() => store.drawerDid, (did) => {
  if (did) panels.closePanelDrawers()
  if (did) themeOpen.value = false
})
watch(() => store.mainTab, () => { themeOpen.value = false })

/* 主题切换：先把新底色铺满再淡出，避免整套 CSS 变量瞬时跳变（结） */
watch(() => [theme.mode, theme.preset, theme.accent], () => {
  void nextTick(() => {
    const stage = getComputedStyle(document.documentElement).getPropertyValue('--stage').trim()
    themeSweep(stage || '#faf9f7')
  })
})

/* 后端未连通时状态点慢慢呼吸，连通后立刻停（停摆 vs 有结果） */
watch(online, (v) => breathe(pingEl.value, !v))

/* 自动化 / 天气抽屉由 store 的布尔量控制，进出交给动效层 */
function onDrawerEnter(el: Element): void {
  drawerEnter(el)
}
function onDrawerLeave(el: Element, done: () => void): void {
  drawerLeave(el, done)
}

/* 外观面板只在一个锚点里，点外面就收起；用 capture 抢在按钮 click 之前判断。 */
function onDocPointerDown(e: Event): void {
  if (!themeOpen.value) return
  const el = actionsEl.value
  if (el && !el.contains(e.target as Node)) themeOpen.value = false
}
function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Escape') themeOpen.value = false
}
function openAbout(): void {
  themeOpen.value = false
  aboutOpen.value = true
}
onMounted(() => {
  document.addEventListener('pointerdown', onDocPointerDown, true)
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  store.stopPolling(); panels.stopPolling(); notices.stopPolling()
  document.removeEventListener('pointerdown', onDocPointerDown, true)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <!-- ③ 登录链路：未登录（含恢复检查、猫跳跃收页）时登录页是唯一内容 -->
  <LoginPage v-if="auth.phase !== 'app'" />

  <!-- ④ 主应用外壳 + ⑥ 四个面板：侧栏 + 顶栏 + 内容区 + 三种互斥抽屉 -->
  <div v-else class="stage">
    <Sidebar />

    <main class="main">
      <header class="topbar m-glass m-glass-rail">
        <div class="top-crumb">
          <span class="section-label">{{ tabLabel }}</span>
        </div>
        <!-- 窄屏侧栏收起时，家庭切换接管顶栏最左（宽屏仍只在侧栏品牌行） -->
        <div class="top-home"><HomeSwitcher /></div>
        <nav class="tabs">
          <button v-for="t in tabNames" :key="t[0]" type="button" class="tab"
                  :class="{ active: store.mainTab === t[0] }" @click="store.setMainTab(t[0])">
            {{ t[1] }}
            <!-- 未读数直接贴在「通知」标签上，不额外占用顶栏一块地方 -->
            <span v-if="t[0] === 'notices' && notices.hasUnread" class="tab-badge">
              {{ notices.badge }}
            </span>
          </button>
        </nav>
        <div class="top-right">
          <span ref="pingEl" class="top-ping mono" :class="{ 'is-on': online }">{{ pingText }}</span>
          <div ref="actionsEl" class="top-actions">
            <button type="button" class="btn sm ghost top-version" :disabled="!appVersion"
                    :title="`关于应用 · v${appVersion}`" aria-haspopup="dialog"
                    @click="openAbout">v{{ appVersion || '—' }}</button>
            <button type="button" class="btn sm ghost" :class="{ active: themeOpen }"
                    :aria-expanded="themeOpen" aria-haspopup="dialog"
                    @click="themeOpen = !themeOpen">主题</button>
            <button type="button" class="btn sm ghost" @click="store.refresh()">刷新设备</button>
            <button type="button" class="btn sm ghost logout" @click="auth.logout()">退出登录</button>
            <ThemePanel v-if="themeOpen" />
          </div>
        </div>
      </header>

      <div class="content">
        <!-- 主标签页切换走「导」语态：旧的先淡出上移，新的再落下 -->
        <Transition :css="false" mode="out-in" @enter="pageEnter" @leave="pageLeave">
          <DeviceGrid v-if="store.mainTab === 'devices'" key="devices" />
          <ScenesPanel v-else-if="store.mainTab === 'scenes'" key="scenes" />
          <AutomationsPanel v-else-if="store.mainTab === 'automations'" key="automations" />
          <NoticesPanel v-else-if="store.mainTab === 'notices'" key="notices" />
          <EventsPanel v-else-if="store.mainTab === 'logs'" key="logs" />
        </Transition>
      </div>
    </main>

    <DeviceDrawer />
    <Transition :css="false" @enter="onDrawerEnter" @leave="onDrawerLeave">
      <AutomationDrawer v-if="panels.autoDrawerOpen" />
    </Transition>
    <Transition :css="false" @enter="onDrawerEnter" @leave="onDrawerLeave">
      <WeatherDrawer v-if="panels.weatherDrawerOpen" />
    </Transition>

    <!-- 新通知在右下角自己报一声，不挡操作；点卡片进详情 -->
    <NoticeToasts />

    <!-- 关于应用 / 在线升级 -->
    <AboutDialog :open="aboutOpen" @close="aboutOpen = false" />

    <div v-if="store.toastMsg" class="toast m-glass">{{ store.toastMsg }}</div>
  </div>
</template>

<style scoped>
/* ② 的主题面板在侧栏里以浮层出现；这里保留 scoped 外壳的最低限度约束，
   组件与网格的细节样式一律写在第 4-7 层，避免两套来源打架。 */
.stage { min-height: 100dvh; background: var(--stage); }
.main { min-height: 100dvh; margin-left: var(--rail-w); display: flex; flex-direction: column; }
.content { flex: 1; padding: 24px; max-width: 1520px; width: 100%; }
.logout { flex: none; }
.top-version {
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--ink-muted);
}
.top-version:hover { color: var(--blue); background: var(--blue-soft); }
@media (max-width: 980px) {
  .main { margin-left: 0; }
  .content { padding: 16px; }
}
</style>
