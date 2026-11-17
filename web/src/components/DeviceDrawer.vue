<script setup lang="ts">
/* 设备详情弹框（居中双列）。与旧界面 syncDrawer 一一对应，只把「每 3 秒整块重建」
 * 换成响应式局部更新；⑤ 把摄像头专项收进这里。
 * 双列分工：左列「状态 → 控制 → 摄像头」，右列「历史趋势 → 显示设置 → 分组」，
 * 列内自上而下即阅读顺序。控制与历史趋势没有内容时整块不出现，不留空占位。 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { categoryOf, CATEGORY_LABELS, sizeOf } from '../devices/cards'
import { optionLabel } from '../devices/labels'
import { curveEntries, formatValue, labelOf, productLabel, readoutEntries, sparkline, switchLabel } from '../devices/readouts'
import type { DeviceControl, DeviceView, Size } from '../devices/types'
import CameraPanel from './CameraPanel.vue'
import CapDialog from './CapDialog.vue'
import ControlBusy from './ControlBusy.vue'
import IrPanel from './IrPanel.vue'
import { drawerEnter, drawerLeave } from '../motion'
import { vCount } from '../motion/countup'
import { useDevicesStore } from '../stores/devices'
import { useDetailStore } from '../stores/detail'

const store = useDevicesStore()
const detail = useDetailStore()
const nameInput = ref('')
const rangeVals = ref<Record<string, number>>({})

const SIZES: Array<[Size, string]> = [['lg', '大'], ['md', '中'], ['sm', '小']]
const RANGES: Array<[number, string]> = [[6, '6 小时'], [24, '24 小时'], [168, '7 天']]

const d = computed<DeviceView | null>(() => store.drawerDevice)
const did = computed(() => store.drawerDid || '')
const live = computed(() => store.live[did.value] || {})
const cat = computed(() => categoryOf(d.value))
const isCamera = computed(() => cat.value === 'camera')
const readouts = computed(() => d.value ? readoutEntries(d.value, live.value) : [])
const curves = computed(() => d.value ? curveEntries(d.value, store.history[did.value] || {}) : [])
const metricKeys = computed<string[]>(() => {
  if (!d.value) return []
  const keys = Object.keys(d.value.readable || {})
  for (const c of d.value.controls || []) {
    if (c.readable && !keys.includes(c.key)) keys.push(c.key)
  }
  return keys
})
const writableControls = computed<DeviceControl[]>(
  () => (d.value?.controls || []).filter((x) => x.writable))
/* 控制区只在「在线 + 真有可操作项」时出现：离线设备的控制项本来就点不动，
   只留一句话等于占着半列版面说「没有」。 */
const hasControls = computed(() => Boolean(
  d.value && d.value.online !== false
  && ((d.value.switches || []).length > 0 || writableControls.value.length > 0),
))
/* 历史趋势要分清「还没拉到」和「确实没采样」：前者不能当作没数据把整块拿掉，
   否则每次打开弹框都会先闪一下再出现。 */
const historyLoaded = computed(() => Boolean(store.historyReady[did.value]))
const showHistory = computed(() => historyLoaded.value && curves.value.length > 0)

const productText = computed(() => {
  if (!d.value) return ''
  // 红外遥控的状态行已经写了品类（电视遥控 · 在线），再来一行「电视遥控（型号）」
  // 是同一句话重复两遍；型号在弹框头部已经有了，这里整行不显示。
  if (d.value.ir) return ''
  // productLabel 按 spec 中文名归一；认不出的英文产品名退到类别名，
  // 不再把 "Bath Heater" 这类云端原文直接露在状态区
  const p = productLabel(d.value) || CATEGORY_LABELS[cat.value] || ''
  const model = d.value.model || ''
  return p + (model && p !== model ? '（' + model + '）' : '')
})
const statusText = computed(() => {
  // 红外遥控是单向发码的虚拟设备，没有开关状态可说，别写「状态未知」
  if (d.value && d.value.ir) {
    return (d.value.ir.label || '红外遥控') + ' · ' + (d.value.online ? '在线' : '离线')
  }
  return (live.value.on === true ? '运行中' : live.value.on === false ? '已关闭' : '状态未知')
    + ' · ' + (d.value?.online ? '在线' : '离线')
})
const sizeNow = computed<Size>(() => {
  if (!d.value) return 'sm'
  return store.layout.sizes[did.value] || sizeOf(d.value)
})
const sizeNote = computed(() => {
  if (!d.value) return false
  const manual = store.layout.sizes[did.value]
  return Boolean(manual && manual !== 'sm' && !store.cardHasContent(d.value, live.value))
})

watch(did, (v) => {
  nameInput.value = v && store.devices[v] ? store.displayName(store.devices[v]) : ''
  rangeVals.value = {}
})
onMounted(() => {
  if (d.value) nameInput.value = store.displayName(d.value)
  window.addEventListener('keydown', onKey)
})
onUnmounted(() => window.removeEventListener('keydown', onKey))
function onEnter(el: Element): void { drawerEnter(el) }
function onLeave(el: Element, done: () => void): void { drawerLeave(el, done) }
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && store.drawerDid) store.closeDrawer()
}

function saveName(): void {
  if (!did.value) return
  store.setName(did.value, nameInput.value)
  store.toast('名称已保存（仅本机）')
}
function restoreName(): void {
  if (!did.value) return
  store.setName(did.value, '')
  nameInput.value = d.value?.name || ''
  store.toast('已恢复云端名称')
}
function rangeValue(c: DeviceControl): number {
  const v = rangeVals.value[c.key]
  if (v !== undefined) return v
  const l = live.value[c.key]
  return (l === undefined || l === null) ? Number(c.min ?? 0) : Number(l)
}
function onRangeInput(c: DeviceControl, e: Event): void {
  rangeVals.value = { ...rangeVals.value, [c.key]: Number((e.target as HTMLInputElement).value) }
}
async function onRangeChange(c: DeviceControl, e: Event): Promise<void> {
  const v = Number((e.target as HTMLInputElement).value)
  /* setControl 内部已含两拍回读：返回时真实状态已落到 live，
   * 这里只需清掉本地临时值，交给回读的真值显示。 */
  const done = await store.setControl(did.value, c, v)
  if (!done) return
  const next = { ...rangeVals.value }
  delete next[c.key]
  rangeVals.value = next
}
/* 模式这类枚举会连带改亮度和色温（吊灯切「傍晚」会把色温一起推到暖白）。
 * setControl 已做两拍回读，这里只需清掉滑块临时值。 */
async function pickEnum(c: DeviceControl, v: unknown): Promise<void> {
  const done = await store.setControl(did.value, c, v)
  if (!done) return
  rangeVals.value = {}
}
function chartSvg(points: Array<[number, number]>): string {
  return sparkline(points, { w: 320, h: 68, color: 'var(--blue)' })
}
function extrema(pts: Array<[number, number]>, key: string): string {
  const nums = pts.map((p) => p[1])
  return '最低 ' + formatValue(key, Math.min(...nums), d.value)
    + ' / 最高 ' + formatValue(key, Math.max(...nums), d.value)
}
async function toggleGroup(id: string, inside: boolean): Promise<void> {
  await store.postGroups({ action: inside ? 'remove' : 'add', id, did: did.value })
}
</script>

<template>
  <!-- 进出交给动效层（放）：遮罩淡入、弹框抬升微缩地弹出 -->
  <Transition :css="false" @enter="onEnter" @leave="onLeave">
    <div v-if="d" class="drawer-layer">
    <div class="drawer-mask" @click="store.closeDrawer()"></div>
    <div class="sheet m-glass m-glass-strong" role="dialog" aria-modal="true"
         aria-label="设备详情">
      <header class="sheet-head">
        <div>
          <h3>{{ store.displayName(d) }}</h3>
          <span class="sheet-cat mono">{{ CATEGORY_LABELS[cat] }} · {{ d.model || '—' }}</span>
        </div>
        <button type="button" class="icon-btn" aria-label="关闭" @click="store.closeDrawer()">
          <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </header>

      <div class="sheet-body">
        <!-- 左列：状态 → 控制 → 摄像头 -->
        <div class="sheet-col">
          <div class="dr-panel m-surface">
            <div class="ctrl-row">
              <label>状态</label>
              <div class="dr-status">{{ statusText }}</div>
              <div class="dim-line">{{ productText }}</div>
            </div>
            <div v-if="readouts.length" class="dr-readouts">
              <div v-for="r in readouts" :key="r.key" class="dr-readout" :class="{ primary: r.primary }">
                <span class="dr-readout-k">{{ r.label }}</span>
                <span v-count class="dr-readout-v">{{ r.text }}</span>
              </div>
            </div>
          </div>

          <!-- 红外遥控：命令与自定义按键都在这里，点一下发一次码 -->
          <IrPanel v-if="d.ir" :did="did" :ir="d.ir" :offline="d.online === false" />

          <div v-if="hasControls" class="dr-panel m-surface ctl-panel">
            <div class="dr-section-label">控制</div>
            <template v-if="(d.switches || []).length > 1">
              <div v-for="(s, i) in (d.switches || [])" :key="s.key" class="ctrl-row">
                <label>{{ switchLabel(s, i) }}</label>
                <button type="button" class="btn sm" :class="{ active: live[s.key] }"
                        @click="store.toggle(did, !live[s.key], s.key)">
                  {{ live[s.key] ? '关闭' : '打开' }}
                </button>
              </div>
            </template>
            <div v-else-if="(d.switches || []).length" class="ctrl-row">
              <label>电源</label>
              <button type="button" class="btn sm" :class="{ active: live.on }"
                      @click="store.toggle(did, !live.on, (d.switches || [])[0]?.key || 'on')">
                {{ live.on ? '关闭' : '打开' }}
              </button>
            </div>
            <div v-for="c in writableControls" :key="c.key" class="ctrl-row">
              <label>{{ c.label }}{{ c.unit ? '（' + c.unit + '）' : '' }}</label>
              <div v-if="c.kind === 'range'" class="ctrl-line">
                <input class="dr-range" type="range" :min="c.min ?? 0" :max="c.max ?? 100"
                       :step="c.step || 1" :value="rangeValue(c)" :aria-label="c.label"
                       @input="onRangeInput(c, $event)"
                       @change="onRangeChange(c, $event)">
                <span class="ctrl-val">{{ rangeValue(c) }}{{ c.unit || '' }}</span>
              </div>
              <button v-else-if="c.kind === 'bool'" type="button" class="btn sm"
                      :class="{ active: live[c.key] }"
                      @click="store.setControl(did, c, !live[c.key])">
                {{ live[c.key] ? '开' : '关' }}
              </button>
              <div v-else-if="c.kind === 'enum'" class="btn-wrap">
                <button v-for="o in c.options || []" :key="String(o.v)" type="button" class="btn sm"
                        :class="{ active: live[c.key] === o.v }"
                        @click="pickEnum(c, o.v)">{{ optionLabel(c.key, o.t) }}</button>
              </div>
            </div>
            <!-- 控制执行中：盖住控制面板拦截点击，等真实状态回读完成再放行 -->
            <ControlBusy :busy="store.isControlling(did)" />
          </div>

          <!-- ⑤ 摄像头专项：与旧界面一致，不区分在线状态，按 spec 动态出按钮 -->
          <CameraPanel v-if="isCamera" :device="d" />
        </div>

        <!-- 右列：历史趋势 → 显示设置 → 自定义分组 -->
        <div class="sheet-col">
          <div v-if="showHistory" class="dr-panel m-surface">
            <div class="dr-history-head">
              <span class="dr-section-label">历史趋势</span>
              <div class="btn-group m-groove">
                <button v-for="r in RANGES"
                        :key="r[0]" type="button" class="btn sm"
                        :class="{ active: store.drawerHours === r[0] }"
                        @click="store.setDrawerHours(r[0])">{{ r[1] }}</button>
              </div>
            </div>
            <div v-for="c in curves.slice(0, 3)" :key="c.key" class="dr-h-item">
              <div class="ct-chart-cap">
                <span>{{ c.label }} · 当前 {{ c.last }}</span>
                <span class="ct-chart-last">{{ extrema(c.points, c.key) }}</span>
              </div>
              <!-- eslint-disable-next-line vue/no-v-html -->
              <div class="ct-chart-svg tall" v-html="chartSvg(c.points)"></div>
            </div>
          </div>

          <div class="dr-panel m-surface">
            <div class="dr-section-label">显示名称</div>
            <div class="ctrl-row">
              <label>自定义名称</label>
              <div class="ctrl-line">
                <input v-model="nameInput" class="field" type="text" :placeholder="d.name"
                       @keyup.enter="saveName">
                <button type="button" class="btn sm" @click="saveName">保存</button>
                <button type="button" class="btn sm ghost" @click="restoreName">恢复云端名</button>
              </div>
            </div>
            <div class="ctrl-row">
              <label>卡片尺寸</label>
              <div class="btn-group m-groove">
                <button v-for="s in SIZES"
                        :key="s[0]" type="button" class="btn sm"
                        :class="{ active: sizeNow === s[0] }" @click="store.setSize(did, s[0])">
                  {{ s[1] }}
                </button>
              </div>
            </div>
            <div v-if="sizeNote" class="dim-note">
              这台设备暂时没有可显示的状态，卡片已自动收为小尺寸；点开详情仍可查看全部信息。
            </div>
            <div v-if="metricKeys.length" class="ctrl-row">
              <label>卡片外显值（最多 2 项）</label>
              <div class="btn-wrap">
                <button v-for="k in metricKeys" :key="k" type="button" class="btn sm"
                        :class="{ active: (store.metrics[did] || []).includes(k) }"
                        @click="store.toggleMetric(did, k)">{{ labelOf(k, d) }}</button>
              </div>
            </div>
          </div>

          <div class="dr-panel m-surface">
            <div class="dr-section-label">自定义分组</div>
            <div v-if="!store.groups.length" class="dim-note">在左侧「自定义分组」点 + 新建。</div>
            <div class="btn-wrap">
              <button v-for="g in store.groups" :key="g.id" type="button" class="btn sm"
                      :class="{ active: (g.dids || []).map(String).includes(did) }"
                      @click="toggleGroup(g.id, (g.dids || []).map(String).includes(did))">
                {{ g.name }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 取流失败弹窗：挂在外层遮罩而不是弹框里 —— 弹框带 backdrop-filter，
         fixed 子元素会相对它定位，弹窗会被裁在弹框宽度内 -->
    <CapDialog :tip="detail.tip" :busy="!!detail.capBusy[did]"
               @close="detail.closeTip()" @retry="detail.retryTip()" />
    </div>
  </Transition>
</template>
