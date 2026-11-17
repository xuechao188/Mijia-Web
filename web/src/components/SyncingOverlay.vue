<script setup lang="ts">
/* 首次扫码登录后的设备同步进度窗口。
 *
 * 后端扫码成功时若被米家风控限流，设备列表可能暂时为空，由后台线程补拉。
 * 此时 devices store 的 syncing 为真：本窗口盖住主界面，明确告诉用户正在取设备，
 * 同时 store 每几秒重拉一次列表，拿到设备后 syncing 转 false，窗口自动消失。
 *
 * 不放关闭按钮、不响应遮罩点击——这是必须等结果的阶段，提前放行只会看到空列表。
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { dialogEnter, dialogLeave, spin } from '../motion'

const ring = ref<HTMLElement | null>(null)

function onEnter(el: Element): void { dialogEnter(el) }
function onLeave(el: Element, done: () => void): void { dialogLeave(el, done) }

onMounted(() => spin(ring.value, true))
onUnmounted(() => spin(ring.value, false))
</script>

<template>
  <Transition :css="false" @enter="onEnter" @leave="onLeave">
    <div class="sync-layer" role="status" aria-live="polite" aria-label="正在获取设备信息">
      <div class="sync-mask"></div>
      <div class="sync-box m-glass m-glass-strong">
        <span ref="ring" class="sync-ring" aria-hidden="true"></span>
        <div class="sync-title">正在获取设备信息</div>
        <div class="sync-sub">请耐心等待，首次登录从米家云端同步设备可能需要一会儿</div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.sync-layer {
  position: fixed; inset: 0; z-index: 20;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.sync-mask { position: absolute; inset: 0; background: var(--overlay); }
.sync-box {
  position: relative; width: min(360px, calc(100vw - 40px));
  padding: 30px 28px 26px; border-radius: var(--r-lg);
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  text-align: center;
}
.sync-ring {
  width: 34px; height: 34px; border-radius: 50%;
  border: 3px solid var(--line-strong); border-top-color: var(--blue);
}
.sync-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.sync-sub { font-size: 12px; line-height: 1.7; color: var(--ink-muted); }
</style>
