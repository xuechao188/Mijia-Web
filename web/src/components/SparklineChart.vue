<script setup lang="ts">
/* 可交互折线图。VIVID 视觉层新增：在纯展示 sparkline 之上补鼠标跟随的
 * 准星线 + 高亮点 + 「时刻 · 数值」气泡。纯展示组件，不触发任何控制，
 * 不改业务状态；hover 只是读取曲线点。沿用 instruments.css 的 .ct-svg 绘制
 * 细节，role=img + aria-label 保证读屏仍拿到整体摘要。 */
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  points: Array<[number, number]>
  format?: (v: number) => string
  timeMode?: 'timestamp' | 'index'   // x 是秒级时间戳还是序号
  labels?: [string, string]          // index 模式首尾标签（可选，用于时刻显示）
  color?: string
  w?: number
  h?: number
}>(), {
  format: (v: number) => String(Math.round(v * 10) / 10),
  timeMode: 'timestamp',
  labels: () => ['', ''],
  color: 'var(--blue)',
  w: 240,
  h: 48,
})

const wrap = ref<HTMLElement | null>(null)
const active = ref<number>(-1)   // 命中的点索引，-1 表示未悬停
const PAD = 4

const P = computed(() => (props.points || []).filter(
  (p) => p && isFinite(p[0]) && isFinite(p[1])))

const xy = computed<Array<[number, number]>>(() => {
  const pts = P.value
  if (!pts.length) return []
  const vals = pts.map((p) => p[1])
  let lo = Math.min(...vals), hi = Math.max(...vals)
  if (hi - lo < 1e-9) { lo -= 1; hi += 1 }
  const span = hi - lo
  const w = props.w, h = props.h
  return pts.map((p, i) => {
    const x = pts.length === 1 ? w / 2 : PAD + i / (pts.length - 1) * (w - PAD * 2)
    const y = h - PAD - (p[1] - lo) / span * (h - PAD * 2)
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10]
  })
})

const line = computed(() => xy.value.map((p) => p[0] + ',' + p[1]).join(' '))
const area = computed(() => {
  const pts = xy.value
  if (!pts.length) return ''
  const base = props.h - PAD
  return 'M' + pts[0][0] + ',' + base + ' L'
    + pts.map((p) => p[0] + ',' + p[1]).join(' L')
    + ' L' + pts[pts.length - 1][0] + ',' + base + ' Z'
})
const gid = computed(() => 'sg' + Math.random().toString(36).slice(2, 8))
const last = computed(() => xy.value[xy.value.length - 1] || null)
const trend = computed(() => {
  const pts = P.value
  if (pts.length < 2) return '平稳'
  const d = pts[pts.length - 1][1] - pts[0][1]
  return d > 0.5 ? '总体上升' : d < -0.5 ? '总体下降' : '基本平稳'
})

function timeLabel(i: number): string {
  const p = P.value[i]
  if (!p) return ''
  if (props.timeMode === 'timestamp') {
    const d = new Date(p[0] * 1000)
    if (isNaN(d.getTime())) return ''
    return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
  }
  // index：用首尾标签线性插值出大致时刻；没有标签就显示序号
  const n = P.value.length
  if (props.labels[0] && props.labels[1] && n > 1) {
    const frac = i / (n - 1)
    const a = props.labels[0], b = props.labels[1]
    if (/^\d{1,2}:\d{2}$/.test(a) && /^\d{1,2}:\d{2}$/.test(b)) {
      const toMin = (s: string) => { const [hh, mm] = s.split(':').map(Number); return hh * 60 + mm }
      const total = toMin(a) + (toMin(b) - toMin(a)) * frac
      const hh = Math.floor(total / 60) % 24, mm = Math.round(total % 60)
      return String(hh).padStart(2, '0') + ':' + String(mm).padStart(2, '0')
    }
  }
  return '第 ' + (i + 1) + ' 点'
}

function onMove(e: PointerEvent): void {
  const el = wrap.value
  const pts = xy.value
  if (!el || !pts.length) return
  const r = el.getBoundingClientRect()
  const xRatio = (e.clientX - r.left) / r.width      // 0..1 相对容器
  const targetX = xRatio * props.w
  let best = 0, bd = Infinity
  for (let i = 0; i < pts.length; i++) {
    const d = Math.abs(pts[i][0] - targetX)
    if (d < bd) { bd = d; best = i }
  }
  active.value = best
}
function onLeave(): void { active.value = -1 }

const activePt = computed(() => active.value >= 0 ? xy.value[active.value] : null)
const tipText = computed(() => active.value >= 0
  ? timeLabel(active.value) + ' · ' + props.format(P.value[active.value][1])
  : '')
const tipX = computed(() => activePt.value ? (activePt.value[0] / props.w * 100) : 0)
const tipTop = computed(() => activePt.value ? (activePt.value[1] / props.h * 100) : 0)
</script>

<template>
  <div ref="wrap" class="spark" @pointermove="onMove" @pointerleave="onLeave"
       @pointercancel="onLeave">
    <svg class="spark-svg" :viewBox="`0 0 ${w} ${h}`" preserveAspectRatio="none"
         role="img" :aria-label="`趋势曲线，${trend}，最低 ${format(Math.min(...P.map(p=>p[1])))}，最高 ${format(Math.max(...P.map(p=>p[1])))}`">
      <defs>
        <linearGradient :id="gid" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="color" stop-opacity="0.26" />
          <stop offset="100%" :stop-color="color" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path :d="area" :fill="`url(#${gid})`" aria-hidden="true" />
      <polyline :points="line" fill="none" :stroke="color" stroke-width="2"
                stroke-linejoin="round" stroke-linecap="round" aria-hidden="true" />
      <circle v-if="!active && last" :cx="last[0]" :cy="last[1]" r="2.6"
              :fill="color" aria-hidden="true" />
      <!-- 准星线 + 高亮点：仅悬停时出现 -->
      <template v-if="activePt">
        <line class="spark-cross" :x1="activePt[0]" y1="0" :x2="activePt[0]" :y2="h" />
        <circle class="spark-dot" :cx="activePt[0]" :cy="activePt[1]" r="3.4" :fill="color" />
      </template>
      <title>{{ trend }}</title>
    </svg>
    <span v-if="active >= 0" class="spark-tip" :style="{ left: tipX + '%', top: tipTop + '%' }">
      {{ tipText }}
    </span>
  </div>
</template>

<style scoped>
.spark { position: relative; width: 100%; height: 100%; }
.spark-svg { width: 100%; height: 100%; display: block; overflow: visible; }
.spark-cross {
  stroke: rgb(var(--tone-rgb) / .55);
  stroke-width: 1; stroke-dasharray: 3 3;
}
.spark-dot { stroke: var(--surface-solid); stroke-width: 1.5; }
.spark-tip {
  position: absolute; z-index: 4;
  transform: translate(-50%, calc(-100% - 10px));
  padding: 4px 8px; border-radius: var(--r-xs);
  background: var(--float-bg); color: var(--ink);
  border: 1px solid var(--card-line);
  box-shadow: var(--e-color-1);
  font-size: 11px; font-weight: 500; line-height: 1.3;
  white-space: nowrap; pointer-events: none;
  font-variant-numeric: tabular-nums;
}
</style>
