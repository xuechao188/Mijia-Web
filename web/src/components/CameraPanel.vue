<script setup lang="ts">
/* 摄像头专项面板。
 *
 * 页面保持精简：打开面板不做任何检测，也不摆状态条。用户点「获取实时画面」
 * 时才由后端判定这台能不能在 PC 上出画面 —— 出得来就播，出不来才弹一次
 * 说明（原因 + 需要满足的条件 + 原始返回）。播不了的原因不进版面。
 *
 * 破坏性动作一律不暴露，取流动作不进按钮列表 —— 与旧界面行为一致。
 */
import { computed, nextTick, onUnmounted, ref, watch } from 'vue'
import {
  DIRECTIONS, NO_PTZ_NOTE, PLACEHOLDER_IDLE, PLACEHOLDER_FAILED, PTZ_SYMBOLS,
  capView, classify, directionAction, streamView,
  type CameraAction,
} from '../devices/camera'
import type { DeviceView } from '../devices/types'
import { actionLabel } from '../devices/labels'
import { useDetailStore } from '../stores/detail'

const props = defineProps<{ device: DeviceView }>()
const detail = useDetailStore()
const videoEl = ref<HTMLVideoElement | null>(null)

const did = computed(() => String(props.device.did))
const actions = computed<CameraAction[]>(() => (props.device.actions || []) as CameraAction[])
const cls = computed(() => classify(actions.value))
const result = computed(() => detail.streams[did.value])
const noteOverride = computed(() => detail.streamNotes[did.value] || '')
const view = computed(() => result.value ? streamView(result.value) : null)
const playable = computed(() => !noteOverride.value && view.value?.mode === 'playable' && !!view.value?.url)
const noteText = computed(() => noteOverride.value || '')
const busy = computed(() => !!detail.streamBusy[did.value])

/* 判定结果只在点过按钮之后才有；有就借它的占位文案，没有就说默认那句。 */
const cap = computed(() => detail.caps[did.value] || null)
const placeholderText = computed(() => {
  if (view.value?.mode === 'fallback') return PLACEHOLDER_FAILED
  return capView(cap.value)?.placeholder || PLACEHOLDER_IDLE
})

function act(a: CameraAction | null): void {
  if (a) void detail.runAction(did.value, a)
}
function symbol(name: string): string {
  return PTZ_SYMBOLS[name] || ''
}
function padAction(name: string): CameraAction | null {
  return directionAction(name, cls.value.ptz)
}

// 抽屉关掉时顺手收掉没关的弹窗，别让它挂在下一次打开上
onUnmounted(() => detail.closeTip())

// 拿到可播地址后主动 play；部分 rtsp/rtmp 浏览器不支持，失败静默。
watch(playable, async (on) => {
  if (!on) return
  await nextTick()
  try { await videoEl.value?.play() } catch { /* 浏览器不支持该地址 */ }
})
</script>

<template>
  <section class="dr-panel m-surface cam-panel">
    <div class="dr-section-label">摄像头</div>

    <div class="cam-video">
      <video ref="videoEl" v-show="playable" class="cam-video-el"
             :src="view?.url || ''" autoplay muted playsinline></video>
      <div v-if="!playable" class="cam-placeholder">{{ placeholderText }}</div>
    </div>

    <div class="cam-btns">
      <button type="button" class="btn sm" :disabled="busy" @click="detail.getStream(did)">
        {{ busy ? '正在检测…' : '获取实时画面' }}
      </button>
      <button type="button" class="btn sm ghost" @click="detail.stopStream(did)">停止取流</button>
    </div>

    <div v-if="noteText" class="cam-note">{{ noteText }}</div>

    <template v-if="cls.ptz.length || cls.others.length">
      <div class="cam-pad">
        <template v-if="cls.ptz.length">
          <div class="cam-pad-title">云台</div>
          <div class="cam-pad-grid">
            <button v-for="name in DIRECTIONS" :key="name" type="button" class="cam-pad-btn"
                    :class="{ empty: !padAction(name) }" :disabled="!padAction(name)"
                    :aria-label="name" @click="act(padAction(name))">
              {{ padAction(name) ? symbol(name) : '' }}
            </button>
          </div>
        </template>
        <div v-if="cls.others.length" class="btn-wrap cam-acts">
          <button v-for="a in cls.others" :key="a.aiid + '-' + a.siid" type="button"
                  class="btn sm cam-act" :title="a.name" @click="act(a)">{{ actionLabel(a.name) }}</button>
        </div>
      </div>
    </template>
    <div v-else class="cam-note">{{ NO_PTZ_NOTE }}</div>
  </section>
</template>
