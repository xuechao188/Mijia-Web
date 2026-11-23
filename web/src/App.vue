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
import SyncingOverlay from './components/SyncingOverlay.vue'
import DataLoadingOverlay from './components/DataLoadingOverlay.vue'
import { useThemeStore } from './stores/theme'
import { useAuthStore } from './stores/auth'
import { useDevicesStore } from './stores/devices'
import { usePanelsStore } from './stores/panels'
import { useNoticesStore } from './stores/notices'
import { drawerEnter, drawerLeave, pageEnter, pageLeave, themeSweep } from './motion'

type Ping = { ok: boolean; version: string }

const appVersion = ref('')
/* 外观面板挂在顶栏右侧的动作组里，点按钮外的任何地方或按 Esc 都收起 */
const themeOpen = ref(false)
/* 关于应用弹窗：点顶栏版本号打开 */
const aboutOpen = ref(false)
const actionsEl = ref<HTMLElement | null>(null)
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
    appVersion.value = data.version || ''
  } catch {
    // 拿不到版本号不影响主流程，版本号按钮保持禁用态即可
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
    <!-- VIVID 流动光晕：v2 demo 同款独立图层，三块高饱和光斑 + 缓慢漂移 + 细网格。
         纯装饰，固定在视口底层，不接管任何交互。 -->
    <div class="ambient" aria-hidden="true">
      <i class="blob b1"></i>
      <i class="blob b2"></i>
      <i class="blob b3"></i>
      <i class="blob b4"></i>
      <div class="grid-bg"></div>
    </div>

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

    <!-- 首次登录后设备尚未拉取回来时盖住主界面，拿到设备自动消失 -->
    <SyncingOverlay v-if="store.syncing" />

    <!-- 设备已就位但实时状态还在回填时盖住主界面，避免看到「未知 / 亮度 0」中间态；
         与 SyncingOverlay 互斥，刷新设备时也会短暂出现 -->
    <DataLoadingOverlay v-if="store.loading && !store.syncing" />

    <div v-if="store.toastMsg" class="toast m-glass">{{ store.toastMsg }}</div>
  </div>
</template>

<style scoped>
/* ② 的主题面板在侧栏里以浮层出现；这里保留 scoped 外壳的最低限度约束，
   组件与网格的细节样式一律写在第 4-7 层，避免两套来源打架。 */
/* VIVID：全站主色氛围光。两枚 radial 光斑固定在视口两角，
   颜色由 --ambient-a/b（跟随主色预设）派生；底下的实色仍是 --stage。
   背景附着在 .stage 上不随内容滚动，长页面也始终有氛围。 */
.stage {
  min-height: 100dvh;
  background-color: var(--stage);
  isolation: isolate; /* 光斑层 z-index:0 与内容分层，不靠大规模改组件 z-index */
}
/* VIVID 光晕层：三块大光斑 blur 后缓慢漂移，颜色由主题色派生，
   切主题时自动变色。fixed 铺满视口、pointer-events:none 不挡交互。 */
.ambient {
  position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none;
}
.blob {
  position: absolute; border-radius: 50%; filter: blur(90px);
  opacity: var(--blob-op); will-change: transform;
}
.blob.b1 {
  width: 640px; height: 640px; top: -220px; left: -180px;
  background: var(--blob-a); animation: drift1 18s ease-in-out infinite alternate;
}
.blob.b2 {
  width: 560px; height: 560px; top: 20%; right: -200px;
  background: var(--blob-b); animation: drift2 22s ease-in-out infinite alternate;
}
.blob.b3 {
  width: 520px; height: 520px; bottom: -200px; left: 30%;
  background: var(--blob-c); animation: drift3 26s ease-in-out infinite alternate;
}
/* b4：顶部居中的横向光斑，专门覆盖顶栏那一带，避免顶部出现纯色断层。
   用主色而非粉紫撞色，并单独调低透明度，让顶栏是淡蓝紫而非突兀的粉带。 */
.blob.b4 {
  width: 860px; height: 420px; top: -240px; left: 38%;
  background: var(--blob-a); opacity: calc(var(--blob-op) * .7);
  animation: drift1 24s ease-in-out infinite alternate;
}
.grid-bg {
  position: absolute; inset: 0;
  background-image:
    linear-gradient(var(--grid-line) 1px, transparent 1px),
    linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse at top, #000, transparent 78%);
  -webkit-mask-image: radial-gradient(ellipse at top, #000, transparent 78%);
}
@keyframes drift1 { to { transform: translate(120px, 80px) scale(1.15); } }
@keyframes drift2 { to { transform: translate(-140px, 60px) scale(1.1); } }
@keyframes drift3 { to { transform: translate(80px, -100px) scale(1.2); } }
@media (prefers-reduced-transparency: reduce) {
  .ambient { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .blob { animation: none; }
}
.main { min-height: 100dvh; margin-left: var(--rail-w); display: flex; flex-direction: column; }
/* 内容区铺满可用宽度：高分屏不再因 max-width 上限而在右侧留白。
   设备网格是 auto-fill minmax(184px,1fr)、统计条是 1fr 弹性列，
   都会随容器加宽自动增加列/拉伸，去掉上限不会让元素无限放大。 */
.content { flex: 1; padding: 24px; width: 100%; }
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
