<script setup lang="ts">
/* 设备控制执行中的进度遮罩。
 *
 * 控制指令发到米家、设备实际动作、状态回读之间存在秒级延迟；store 在此期间
 * 按设备置锁、拒绝重复指令。本组件盖住对应卡片/控制面板，明确告诉用户正在
 * 执行，并拦截点击（pointer），避免用户点到过期状态再发一条相反指令。
 *
 * 转圈交给动效层的 spin()：减弱动效时自然停住。遮罩本身不提供关闭入口——
 * 这是必须等回读完成的阶段。 */
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { spin, spinEdge } from '../motion'

const props = withDefaults(defineProps<{
  busy: boolean
  label?: string
}>(), { label: '正在控制…' })

const ring = ref<HTMLElement | null>(null)
const edge = ref<HTMLElement | null>(null)

/* 动态挂载/卸载时元素引用会变，用 nextTick 后重新绑定转圈状态。
   中央 spinner 与四周描边环同步起停，都由 motion 层统一管理（含减弱动效降级）。 */
function syncSpin(on: boolean): void {
  void nextTick(() => {
    spin(ring.value, on)
    spinEdge(edge.value, on)
  })
}
watch(() => props.busy, (v) => syncSpin(v))
onMounted(() => { if (props.busy) syncSpin(true) })
onBeforeUnmount(() => {
  spin(ring.value, false)
  spinEdge(edge.value, false)
})
</script>

<template>
  <Transition name="cb-fade">
    <div v-if="busy" class="cb-layer" role="status" aria-live="polite">
      <!-- 四周彩色旋转描边：conic-gradient + mask 抠出 2.5px 边框，
           起点角 --ang 由 motion.spinEdge 驱动。aria-hidden，纯装饰。 -->
      <span ref="edge" class="cb-edge" aria-hidden="true"></span>
      <div class="cb-veil"></div>
      <div class="cb-inner">
        <span ref="ring" class="cb-ring" aria-hidden="true"></span>
        <span class="cb-label">{{ label }}</span>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.cb-layer {
  position: absolute; inset: 0; z-index: 8;
  display: flex; align-items: center; justify-content: center;
  border-radius: inherit;
}
/* VIVID：四周彩色旋转描边。conic-gradient 起点角 --ang 由 GSAP 连续补间；
   mask 把实心圆抠成 2.5px 宽的边框环，只沿卡片轮廓着色，不遮内容。
   颜色取自 --spin-c1/c2/c3（跟随主色预设），z-index 高于 veil。 */
.cb-edge {
  position: absolute; inset: 0; z-index: 2;
  border-radius: inherit;
  padding: 2.5px;
  pointer-events: none;
  background: conic-gradient(from var(--ang),
    transparent 0deg,
    var(--spin-c1) 50deg, var(--spin-c2) 110deg,
    var(--spin-c3) 170deg, var(--spin-c1) 230deg,
    var(--spin-c2) 290deg, transparent 360deg);
  -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
  -webkit-mask-composite: xor; mask-composite: exclude;
}
.cb-veil {
  position: absolute; inset: 0;
  background: var(--overlay);
  border-radius: inherit;
}
.cb-inner {
  position: relative; z-index: 3;
  display: flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 12px 16px;
}
.cb-ring {
  width: 26px; height: 26px; border-radius: 50%;
  border: 3px solid var(--line-strong); border-top-color: var(--blue);
}
.cb-label {
  font-size: 12px; font-weight: 600; color: var(--ink);
  white-space: nowrap;
}
.cb-fade-enter-active, .cb-fade-leave-active { transition: opacity var(--t-fast) var(--ease); }
.cb-fade-enter-from, .cb-fade-leave-to { opacity: 0; }
</style>
