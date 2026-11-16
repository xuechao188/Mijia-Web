<script setup lang="ts">
/* 设备网格：筛选结果 -> 卡片模型 -> 固定行高网格，外加拖拽顺序持久化。
 * ⑥ 把天气卡放回网格首位（与旧版 renderGrid 一样：仅在全部设备、无搜索时显示）。 */
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { buildCard } from '../devices/content'
import type { CardModel } from '../devices/content'
import { parseKey } from '../devices/groups'
import DeviceCard from './DeviceCard.vue'
import WeatherCard from './WeatherCard.vue'
import { captureRects, flipCards, releaseCards } from '../motion'
import { useDevicesStore } from '../stores/devices'
import { usePanelsStore } from '../stores/panels'

const store = useDevicesStore()
const panels = usePanelsStore()
/* 天气是全局信息，不属于任何房间：家庭 / 全部设备这一层显示，
   进到具体房间或分组就不再占首格。store 里 'all' 会被校准成当前家庭，
   所以只认字面 'all' 会让这张卡永远出不来。 */
const showWeather = computed(() => {
  const t = parseKey(store.filter).type
  return (t === 'all' || t === 'home') && !store.kw && !store.statFilter
    && panels.weather !== null
})
const draggingDid = ref<string | null>(null)
const hoverDid = ref<string | null>(null)
const gridEl = ref<HTMLElement | null>(null)
/* 拖拽前的卡片矩形，换序后用它算 FLIP 位移 */
let beforeRects: Map<string, DOMRect> | null = null

const cards = computed<CardModel[]>(() => store.visible.map((d) => buildCard(d, {
  live: store.live[String(d.did)] || {},
  history: store.history[String(d.did)] || {},
  names: store.names,
  metrics: store.metrics[String(d.did)] || [],
  sizes: store.layout.sizes,
  homesCount: store.homesCount,
})))

/* 格子数随「本范围内有哪几类设备」变化：设备 + 在线两格固定，
   类型组按实际存在的算（空组不占位），在线率格另加宽。 */
const stripStyle = computed(() => ({
  '--stat-cols': String(store.typeStats.length + 2),
}))

/* 计数格按下去筛选卡片；再点同一个口子取消。在线率格是仪表，不参与筛选。 */
function isSel(k: string): boolean {
  return store.statFilter === k
}

/* 在线率只在有设备时才有意义；没设备时读 0%，轨道保持空槽不做假填充 */
const onlineRate = computed(() => {
  const { total, online } = store.stats
  return total ? Math.round((online / total) * 100) : 0
})

function deviceOf(did: string) {
  return store.devices[did] || null
}

/* 放：卡片入场。切家庭/筛选/搜索时整批重播，轮询新设备只补播自己。 */
function release(replay: boolean): void {
  void nextTick(() => releaseCards(gridEl.value, { replay }))
}
onMounted(() => { release(false) })
watch(() => [store.filter, store.home, store.kw, store.statFilter], () => release(true))
watch(() => cards.value.length, (n, old) => { if (n > old) release(false) })

/* 结：换序后按差值补位，让人看清「哪张卡让出了位置」 */
watch(() => cards.value.map((c) => c.did).join('|'), async () => {
  if (!beforeRects) return
  const before = beforeRects
  beforeRects = null
  await nextTick()
  flipCards(gridEl.value, before)
})

/* 停摆语态交给底部的铭牌灯（App.vue）：整条统计板一起呼吸太吵，
   而灯只是一个小点，用来表示「还在等云端回话」正合适。 */

function onDragStart(e: DragEvent, did: string): void {
  draggingDid.value = did
  ;(e.currentTarget as HTMLElement).classList.add('dragging')
  if (e.dataTransfer) {
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', did)
  }
}
function onDragEnd(e: DragEvent): void {
  (e.currentTarget as HTMLElement).classList.remove('dragging')
  draggingDid.value = null
  hoverDid.value = null
}
function cardUnder(e: DragEvent): string | null {
  const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null
  const card = el?.closest?.('.device-card') as HTMLElement | null
  if (!card || !card.dataset.did || card.dataset.did === draggingDid.value) return null
  return card.dataset.did
}
function onDragOver(e: DragEvent): void {
  if (!draggingDid.value) return
  e.preventDefault()
  hoverDid.value = cardUnder(e)
}
function onDrop(e: DragEvent): void {
  e.preventDefault()
  const drag = draggingDid.value
  if (!drag) return
  const tgt = cardUnder(e)
  const order = store.orderedDids()
  const from = order.indexOf(drag)
  if (from < 0) return
  order.splice(from, 1)
  let idx = order.length
  if (tgt) {
    const j = order.indexOf(tgt)
    if (j >= 0) idx = j
  }
  order.splice(idx, 0, drag)
  beforeRects = captureRects(gridEl.value)
  void store.saveOrder(order)
  hoverDid.value = null
  draggingDid.value = null
}
</script>

<template>
  <section class="device-page">
    <!-- 仪器条：当前范围的读数（家庭/房间/搜索都算），按常用类型分组。
         顺序固定 照明 → 环境 → 传感器 → 其它，没有的组不占格子。
         每格都是一颗按钮：按下去只看这一类，再按一次取消。 -->
    <div class="stat-strip m-rail" :style="stripStyle">
      <button type="button" class="stat-cell is-tap" :class="{ 'is-sel': !store.statFilter }"
              :aria-pressed="!store.statFilter" title="显示全部设备"
              @click="store.clearStatFilter()">
        <span class="stat-k">设备</span>
        <b class="stat-v">{{ store.stats.total }}</b>
        <span class="stat-sub" :class="{ hot: store.stats.on > 0 }">
          开 {{ store.stats.on }}
        </span>
      </button>
      <button type="button" class="stat-cell is-tap" :class="{ 'is-sel': isSel('online') }"
              :aria-pressed="isSel('online')" title="只看在线设备"
              @click="store.toggleStatFilter('online')">
        <span class="stat-k">在线</span>
        <b class="stat-v">{{ store.stats.online }}</b>
      </button>
      <button v-for="g in store.typeStats" :key="g.key" type="button"
              class="stat-cell is-tap" :class="{ 'is-sel': isSel(g.key) }"
              :aria-pressed="isSel(g.key)" :title="'只看' + g.label + '设备'"
              @click="store.toggleStatFilter(g.key)">
        <span class="stat-k">{{ g.label }}</span>
        <b class="stat-v">{{ g.count }}</b>
      </button>
      <div class="stat-cell is-rate">
        <span class="stat-k">在线率</span>
        <div class="stat-rate">
          <b class="stat-v sm">{{ onlineRate }}<i class="stat-u">%</i></b>
          <span class="stat-track" role="img" :aria-label="'在线率 ' + onlineRate + '%'">
            <span class="stat-bar" :style="{ width: onlineRate + '%' }"></span>
          </span>
        </div>
      </div>
    </div>

    <!-- 筛选中时给一条可退出的说明：格子上的高亮不够显眼，也不该让人猜怎么回全部 -->
    <div v-if="store.statFilter" class="stat-filter">
      <span class="sf-k">只看</span>
      <b class="sf-v">{{ store.statFilterLabel }}</b>
      <span class="sf-n mono">{{ store.visible.length }} 台</span>
      <button type="button" class="sf-clear" @click="store.clearStatFilter()">显示全部</button>
    </div>

    <div v-if="!store.visible.length" class="grid-tip">
      {{ store.syncing ? '正在从云端同步设备列表…'
        : (store.statFilter ? '当前范围没有' + store.statFilterLabel + '设备'
          : (store.filter !== 'all' || store.kw ? '没有匹配的设备' : '暂无设备')) }}
    </div>

    <div ref="gridEl" class="grid" @dragover="onDragOver" @drop="onDrop">
      <WeatherCard v-if="showWeather" :w="panels.weather" :size="panels.weatherSize" />
      <template v-for="m in cards" :key="m.did">
        <DeviceCard v-if="deviceOf(m.did)" :model="m" :device="deviceOf(m.did)!"
                    :class="{ 'drop-before': hoverDid === m.did }"
                    @dragstart="onDragStart($event, m.did)" @dragend="onDragEnd"
                    @open="store.openDrawer" />
      </template>
    </div>
  </section>
</template>
