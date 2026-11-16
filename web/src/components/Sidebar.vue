<script setup lang="ts">
/* 侧栏：家庭切换、搜索、房间列表与自定义分组。
 *
 * 家庭只在顶部切换，列表里只出现当前家庭的房间（米家的层级做法），
 * 因此不再有「家庭 → 房间」两级缩进。自定义分组跨家庭，单独一栏。
 * 主题、刷新、退出都在顶栏右侧，这里只管导航。 */
import { nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import HomeSwitcher from './HomeSwitcher.vue'
import { useDevicesStore } from '../stores/devices'
import { key as gkey } from '../devices/groups'
import type { DeviceGroup } from '../devices/types'

const store = useDevicesStore()

/* 选中位由一根滑动的竖条承担，而不是每项各画一条内阴影：
 * 条只移动不重绘，切房间时视线跟着它走。几何量在 DOM 里量，
 * 不猜行高，房间增删或换行都不会错位。 */
const navEl = ref<HTMLElement | null>(null)
const barTop = ref(0)
const barH = ref(0)
const barOn = ref(false)
/* 首帧量完再开过渡，否则挂载时那条竖条会从顶上滑下来 */
const barLive = ref(false)
let ro: ResizeObserver | null = null

function measure(): void {
  const nav = navEl.value
  const el = nav?.querySelector('.room-item.active') as HTMLElement | null
  if (!nav || !el) { barOn.value = false; return }
  barTop.value = el.offsetTop + 6
  barH.value = Math.max(12, el.offsetHeight - 12)
  barOn.value = true
}
onMounted(() => {
  void nextTick(() => {
    measure()
    requestAnimationFrame(() => { barLive.value = true })
  })
  if (typeof ResizeObserver !== 'undefined' && navEl.value) {
    ro = new ResizeObserver(() => measure())
    ro.observe(navEl.value)
  }
})
onUnmounted(() => { ro?.disconnect() })
/* 选中项换了、房间列表长短变了、分组增删了，都要重新量 */
watch(() => [
  store.filter,
  store.roomNav.map((n) => n.key + n.count).join('|'),
  store.groups.map((g) => g.id + (g.dids || []).length).join('|'),
], () => void nextTick(measure))

async function createGroup(): Promise<void> {
  const name = (window.prompt('新分组名称') || '').trim()
  if (!name) return
  await store.postGroups({ action: 'create', name })
}
async function deleteGroup(g: DeviceGroup): Promise<void> {
  if (!window.confirm('删除分组「' + g.name + '」？设备不会被删除。')) return
  const ok = await store.postGroups({ action: 'delete', id: g.id })
  if (ok && store.filter === gkey('group', g.id)) store.setFilter('all')
}
</script>

<template>
  <aside class="rail m-rail">
    <div class="rail-brand">
      <div class="brand-txt">
        <strong>米家Web版</strong>
        <span class="mono brand-tag">设备控制台</span>
      </div>
      <HomeSwitcher />
    </div>

    <div class="rail-search">
      <input v-model="store.kw" class="field" type="search" placeholder="搜索设备…" aria-label="搜索设备">
    </div>

    <nav ref="navEl" class="rail-nav">
      <span class="nav-slider" :class="{ 'is-live': barLive }" aria-hidden="true"
            :style="{ transform: 'translateY(' + barTop + 'px)',
                      height: barH + 'px',
                      opacity: barOn ? 1 : 0 }"></span>
      <div class="nav-section"><span>房间</span></div>
      <div v-for="n in store.roomNav" :key="n.key"
           class="room-item" :class="['nav-' + n.type, { active: store.filter === n.key }]"
           @click="store.setFilter(n.key)">
        <span class="nav-label" :title="n.label">{{ n.label }}</span>
        <span class="nav-count mono">{{ n.count }}</span>
      </div>
      <div v-if="!store.roomNav.length" class="nav-hint">暂无房间</div>

      <div class="nav-section">
        <span>自定义分组</span>
        <button type="button" class="nav-add" title="新建分组" aria-label="新建分组"
                @click="createGroup">+</button>
      </div>
      <div v-for="g in store.groups" :key="g.id"
           class="room-item nav-group" :class="{ active: store.filter === gkey('group', g.id) }"
           @click="store.setFilter(gkey('group', g.id))">
        <span class="nav-label" :title="g.name">{{ g.name }}</span>
        <span class="nav-count mono">{{ (g.dids || []).length }}</span>
        <button type="button" class="nav-del" title="删除分组" aria-label="删除分组"
                @click.stop="deleteGroup(g)">×</button>
      </div>
      <div v-if="!store.groups.length" class="nav-hint">还没有分组</div>
    </nav>
  </aside>
</template>
