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
import { spin } from '../motion'

const props = withDefaults(defineProps<{
  busy: boolean
  label?: string
}>(), { label: '正在控制…' })

const ring = ref<HTMLElement | null>(null)

/* 动态挂载/卸载时元素引用会变，用 nextTick 后重新绑定转圈状态。 */
function syncSpin(on: boolean): void {
  void nextTick(() => { spin(ring.value, on) })
}
watch(() => props.busy, (v) => syncSpin(v))
onMounted(() => { if (props.busy) syncSpin(true) })
onBeforeUnmount(() => { spin(ring.value, false) })
</script>

<template>
  <Transition name="cb-fade">
    <div v-if="busy" class="cb-layer" role="status" aria-live="polite">
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
.cb-veil {
  position: absolute; inset: 0;
  background: var(--overlay);
  border-radius: inherit;
}
.cb-inner {
  position: relative;
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
