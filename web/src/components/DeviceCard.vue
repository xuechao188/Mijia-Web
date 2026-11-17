<script setup lang="ts">
/* 单张设备卡。只渲染 buildCard() 算好的模型，不自己判断内容预算。
 * 类名沿用旧界面（dc-/ct- 前缀），样式在第 4/5 层里重做，视觉规则不变：
 * 图标与类型色、名称两行、状态区重排、离线零控件、空壳收成单格。 */
import { computed, ref } from 'vue'
import { CATEGORY_LABELS } from '../devices/cards'
import { svg as iconSvg } from '../devices/icons'
import { sparkline, switchLabel } from '../devices/readouts'
import type { CardModel } from '../devices/content'
import type { DeviceControl, DeviceView, LiveState } from '../devices/types'
import { vCount } from '../motion/countup'
import { useDevicesStore } from '../stores/devices'
import ControlBusy from './ControlBusy.vue'

const props = defineProps<{ model: CardModel; device: DeviceView }>()
const emit = defineEmits<{
  open: [did: string]
  dragstart: [event: DragEvent]
  dragend: [event: DragEvent]
}>()
const store = useDevicesStore()

/* 卡片整体可拖（HTML5 draggable），而滑块/按钮是原生交互控件。
   浏览器会在「按下的元素落在可拖动祖先内」时发起原生 dragstart，
   子元素的 @pointerdown.stop 只挡冒泡、挡不住这条原生拖拽。
   因此在捕获阶段记录真实按下的目标，dragstart 时若命中控件则取消卡片拖动，
   让 input[type=range]/button 自己处理拖动，避免一拖滑块就整卡跟着走。 */
const pressTarget = ref<HTMLElement | null>(null)
function onPointerDownCapture(e: PointerEvent): void {
  pressTarget.value = e.target as HTMLElement
}
function onCardDragStart(e: DragEvent): void {
  const el = pressTarget.value
  pressTarget.value = null
  if (el && el.closest('input, button, .ct-slider-row, .ct-stepper-row, .chip, .mini-switch')) {
    e.preventDefault()
    return
  }
  emit('dragstart', e)
}

const dragVals = ref<Record<string, number>>({})

const live = computed<LiveState>(() => store.live[props.model.did] || {})
const busy = computed(() => store.isControlling(props.model.did))
const icon = computed(() => iconSvg(props.model.cat))
const catLabel = computed(() => CATEGORY_LABELS[props.model.cat] || '')
const singleSwitch = computed(() => props.model.showSwitch && !props.model.multi && !props.model.offline)
const hasClassContent = computed(() => Boolean(
  props.model.reads.length || props.model.ctrls.length || props.model.curves.length
  || props.model.chips.length || props.model.switches.length || props.model.ir.length,
))

function currentOf(c: DeviceControl): number {
  const v = dragVals.value[c.key]
  if (v !== undefined) return v
  const l = live.value[c.key]
  return (l === undefined || l === null) ? Number(c.min ?? 0) : Number(l)
}
function onSliderPointerDown(e: PointerEvent): void {
  // 捕获指针：即使拖动中指针移出滑块，pointerup 仍会回到这里，避免 setHold 残留 true
  ;(e.currentTarget as HTMLInputElement).setPointerCapture?.(e.pointerId)
  store.setHold(props.model.did, true)
}
function onSliderPointerUp(): void {
  store.setHold(props.model.did, false)
}
function onSliderInput(c: DeviceControl, e: Event): void {
  dragVals.value = { ...dragVals.value, [c.key]: Number((e.target as HTMLInputElement).value) }
}
function onSliderChange(c: DeviceControl, e: Event): void {
  const v = Number((e.target as HTMLInputElement).value)
  const next = { ...dragVals.value }
  delete next[c.key]
  dragVals.value = next
  store.setHold(props.model.did, false)
  void store.setControl(props.model.did, c, v)
}
function step(c: DeviceControl, delta: number): void {
  const cur = currentOf(c)
  const size = Number(c.step) || 1
  const next = Math.max(Number(c.min ?? 0), Math.min(Number(c.max ?? 100), cur + delta * size))
  if (next === cur) return
  dragVals.value = { ...dragVals.value, [c.key]: next }
  void store.setControl(props.model.did, c, next)
  setTimeout(() => {
    const n = { ...dragVals.value }
    delete n[c.key]
    dragVals.value = n
  }, 0)
}
function chartSvg(points: Array<[number, number]>): string {
  return sparkline(points, { w: 240, h: 48, color: 'var(--blue)' })
}
</script>

<template>
  <article
    class="device-card"
    :class="[
      model.isOn ? 'on' : 'off',
      model.offline ? 'offline' : '',
      model.bare ? 'is-bare' : '',
      'sz-' + model.size, 'cat-' + model.cat,
    ]"
    :data-did="model.did"
    :data-category="model.cat"
    :data-size="model.size"
    draggable="true"
    @click="emit('open', model.did)"
    @pointerdown.capture="onPointerDownCapture"
    @dragstart="onCardDragStart"
    @dragend="emit('dragend', $event)"
  >
    <header class="dc-head">
      <div class="dc-icon" :title="catLabel" v-html="icon"></div>
      <div class="dc-titles">
        <div class="dc-name" :title="model.name">{{ model.name }}</div>
        <div v-if="model.subText" class="dc-sub"
             :class="{ 'is-offline': model.offline, 'is-context': !model.subIsStatus }">
          <span v-if="model.subIsStatus" class="dot"></span>{{ model.subText }}
        </div>
      </div>
      <button v-if="singleSwitch" type="button" class="mini-switch in-head"
              :class="{ on: model.isOn }" title="开关" aria-label="开关"
              @click.stop="store.toggle(model.did, !model.isOn, (device.switches || [])[0]?.key || 'on')">
      </button>
    </header>

    <!-- 多键开关：逐路独立，最多铺 4 路 -->
    <div v-if="model.switches.length" class="dc-switches">
      <div v-for="(s, i) in model.switches" :key="s.key" class="sw-row">
        <span class="sw-label" :title="switchLabel(s, i)">{{ switchLabel(s, i) }}</span>
        <button type="button" class="mini-switch" :class="{ on: live[s.key] === true }"
                :title="s.label || s.key" :aria-label="switchLabel(s, i)"
                @click.stop="store.toggle(model.did, live[s.key] !== true, s.key)"></button>
      </div>
    </div>
    <div v-if="model.switchMore" class="sw-more">另有 {{ model.switchMore }} 路，点开设备控制</div>

    <!-- 枚举快捷操作 -->
    <div v-if="model.chips.length" class="dc-actions">
      <button v-for="chip in model.chips" :key="chip.key" type="button"
              class="chip" :class="{ active: chip.active, swing: chip.swing }"
              @click.stop="store.setControl(model.did, chip.control, chip.value)">
        {{ chip.label }}
      </button>
    </div>

    <!-- 红外遥控：点一下发一次码。没有状态，所以不做选中态、不显示开关。 -->
    <div v-if="model.ir.length" class="dc-actions dc-ir">
      <button v-for="cmd in model.ir" :key="cmd.id" type="button"
              class="chip ir-chip" :title="cmd.label"
              @click.stop="store.pressIr(model.did, cmd)">
        {{ cmd.label }}
      </button>
    </div>

    <!-- 大卡：有分类内容压成一行档案，否则保留四行设备信息 -->
    <div v-if="model.size === 'lg' && !model.bare && hasClassContent" class="ct-info">
      {{ model.info }}
    </div>
    <div v-else-if="model.size === 'lg' && !model.bare" class="dc-detail">
      <div v-for="[k, v] in model.detailRows" :key="k" class="dc-detail-row">
        <span class="dc-detail-k">{{ k }}</span>
        <span class="dc-detail-v" :title="v">{{ v }}</span>
      </div>
    </div>

    <div v-if="model.reads.length" class="ct-readouts">
      <div v-for="r in model.reads" :key="r.key" class="ct-metric" :class="{ primary: r.primary }">
        <span class="ct-metric-k">{{ r.label }}</span>
        <span v-count class="ct-metric-v">{{ r.text }}</span>
      </div>
    </div>

    <div v-if="model.ctrls.length" class="ct-controls">
      <div v-for="c in model.ctrls" :key="c.key">
        <div v-if="c.key === 'target-temperature'" class="ct-stepper-row" @click.stop>
          <span class="ct-slider-k">{{ c.label }}</span>
          <div class="ct-stepper">
            <button type="button" class="ct-step" aria-label="减小" @click.stop="step(c, -1)">
              <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg>
            </button>
            <span class="ct-stepper-v">{{ currentOf(c) }}{{ c.unit || '' }}</span>
            <button type="button" class="ct-step" aria-label="增大" @click.stop="step(c, 1)">
              <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M5 12h14"/></svg>
            </button>
          </div>
        </div>
        <div v-else class="ct-slider-row" @click.stop>
          <div class="ct-slider-head">
            <span class="ct-slider-k">{{ c.label }}</span>
            <span class="ct-slider-v">{{ currentOf(c) }}{{ c.unit || '' }}</span>
          </div>
          <input class="ct-range" type="range" draggable="false" :min="c.min ?? 0" :max="c.max ?? 100"
                 :step="c.step || 1" :value="currentOf(c)"
                 :aria-label="c.label"
                 @pointerdown.stop="onSliderPointerDown"
                 @pointerup.stop="onSliderPointerUp"
                 @pointercancel.stop="onSliderPointerUp"
                 @input="onSliderInput(c, $event)" @change="onSliderChange(c, $event)">
        </div>
      </div>
    </div>

    <div v-if="!model.bare && model.size === 'lg'" class="dc-extra">
      <div v-if="model.curves.length" class="ct-chart">
        <div class="ct-chart-cap">
          <span>{{ model.curves[0].label }}趋势</span>
          <span class="ct-chart-last">{{ model.curves[0].last }}</span>
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="ct-chart-svg" v-html="chartSvg(model.curves[0].points)"></div>
      </div>
      <div v-else-if="model.curveHint" class="ct-chart-empty">{{ model.curveHint }}</div>
    </div>

    <!-- 控制执行中：盖住整卡拦截点击，防止状态回读完成前重复下发相反指令 -->
    <ControlBusy :busy="busy" />
  </article>
</template>
