<script setup lang="ts">
/* 环形仪表。VIVID 视觉层的新组件：SVG stroke-dasharray 画主色圆弧，
 * 中央读数（数字 + 单位）水平单行居中。纯展示，无交互，不改任何业务状态。
 * 数值用 vCount 滚动，与卡片读数同一套语态。 */
import { computed } from 'vue'
import { vCount } from '../motion/countup'

const props = withDefaults(defineProps<{
  value: number          // 0-100
  size?: number          // 外径 px
  label?: string         // 环下方的说明（可选）
  unit?: string          // 数字后单位，默认 %
}>(), { size: 46, label: '', unit: '%' })

const R = 34
const C = 2 * Math.PI * R
const pct = computed(() => Math.max(0, Math.min(100, Number(props.value) || 0)))
const offset = computed(() => C * (1 - pct.value / 100))
const box = computed(() => `${props.size}px`)
</script>

<template>
  <div class="gauge-ring" :style="{ '--gr-size': box, width: box, height: box }">
    <svg :viewBox="`0 0 80 80`" aria-hidden="true" focusable="false">
      <circle class="gr-track" cx="40" cy="40" :r="R" />
      <circle class="gr-val" cx="40" cy="40" :r="R"
              :stroke-dasharray="C.toFixed(1)" :stroke-dashoffset="offset.toFixed(1)" />
    </svg>
    <div class="gr-num">
      <span v-count>{{ Math.round(pct) }}</span><small>{{ unit }}</small>
    </div>
    <span v-if="label" class="gr-label">{{ label }}</span>
  </div>
</template>

<style scoped>
.gauge-ring {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
}
.gauge-ring svg {
  width: 100%;
  height: 100%;
  transform: rotate(-90deg);
  overflow: visible;
}
.gr-track {
  fill: none;
  stroke: rgb(var(--tone-rgb) / .12);
  stroke-width: 6;
}
.gr-val {
  fill: none;
  stroke: var(--blue);
  stroke-width: 6;
  stroke-linecap: round;
  transition: stroke-dashoffset var(--t-slow) var(--ease);
}
.gr-num {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
  font-size: calc(var(--gr-size) * .34);
  font-weight: 600;
  line-height: 1;
  color: var(--ink);
}
.gr-num small {
  margin-left: 1px;
  font-size: .58em;
  font-weight: 500;
  color: var(--ink-soft);
}
.gr-label {
  position: absolute;
  bottom: -14px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  color: var(--ink-faint);
  white-space: nowrap;
}
@media (prefers-reduced-motion: reduce) {
  .gr-val { transition: none; }
}
</style>
