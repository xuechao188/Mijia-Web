<script setup lang="ts">
/* 首屏设备状态加载进度窗口。
 *
 * bootstrap 并行拉取：设备列表一到就先渲染卡片，而实时状态（/api/live 需
 * 云端批量读属性）往往晚几秒才回来。这段窗口里 live 为空，卡片状态显示
 * 「未知」、亮度滑块回退到 0，容易误以为设备故障。本窗口在 store.loading
 * 为真时盖住主界面，明确告诉用户数据加载中，状态回填完成后自动消失。
 *
 * 与 SyncingOverlay 互斥：正在拉设备列表时由那个窗口负责；本窗口只在
 * 设备已就位、状态尚未回填时显示。不放关闭按钮、不响应遮罩点击。
 */
import { onMounted, onUnmounted, ref } from 'vue'
import { spin } from '../motion'

const ring = ref<HTMLElement | null>(null)

onMounted(() => spin(ring.value, true))
onUnmounted(() => spin(ring.value, false))
</script>

<template>
  <div class="data-load-layer" role="status" aria-live="polite" aria-label="数据正在加载中">
    <div class="data-load-mask"></div>
    <div class="data-load-box m-glass m-glass-strong">
      <span ref="ring" class="data-load-ring" aria-hidden="true"></span>
      <div class="data-load-title">数据正在加载中</div>
      <div class="data-load-sub">请稍后，设备状态同步完成后将自动显示</div>
    </div>
  </div>
</template>

<style scoped>
.data-load-layer {
  position: fixed; inset: 0; z-index: 19;
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.data-load-mask { position: absolute; inset: 0; background: var(--overlay); }
.data-load-box {
  position: relative; width: min(360px, calc(100vw - 40px));
  padding: 30px 28px 26px; border-radius: var(--r-lg);
  display: flex; flex-direction: column; align-items: center; gap: 14px;
  text-align: center;
}
.data-load-ring {
  width: 34px; height: 34px; border-radius: 50%;
  border: 3px solid var(--line-strong); border-top-color: var(--blue);
}
.data-load-title { font-size: 16px; font-weight: 600; color: var(--ink); }
.data-load-sub { font-size: 12px; line-height: 1.7; color: var(--ink-muted); }
</style>
