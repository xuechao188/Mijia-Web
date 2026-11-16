<script setup lang="ts">
/* 登录猫（Vue 版，3D 位图）。
 * 猫体是 assets/cat-orange.webp（橘猫），固定不动；只有眼球由 SVG 覆盖层驱动，
 * 瞳孔跟着鼠标平移。几何与台词来自 login/cat.ts。
 * 对外动作仍是 say / poke / playIn，状态由父组件 mood prop 驱动。 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  eyeOverlay, EYE_FOCUS, MOODS, PUPIL_MAX, pickLine, pupilShift,
  type Mood,
} from '../login/cat'
import catPhoto from '../assets/cat-orange.webp'

const props = defineProps<{ mood?: Mood }>()

const host = ref<HTMLElement | null>(null)
const current = computed<Mood>(() =>
  props.mood && MOODS.includes(props.mood) ? props.mood : 'idle',
)
const eyesMarkup = eyeOverlay()

const bubbleText = ref('')
const bubbleShow = ref(false)

let lineN = 0
let sayTimer: ReturnType<typeof setTimeout> | null = null
let hopTimer: ReturnType<typeof setTimeout> | null = null
let going = false
let raf = 0
let queued = false
let lastEvent: MouseEvent | null = null

function say(text: string, ms = 1900): void {
  bubbleText.value = String(text || '')
  bubbleShow.value = true
  if (sayTimer) clearTimeout(sayTimer)
  sayTimer = setTimeout(() => {
    bubbleShow.value = false
    sayTimer = null
  }, ms)
}

function poke(): void {
  lineN++
  // 直接改 DOM class：Vue 的响应式 class 更新是异步的，
  // 用 ref 做不到「同一帧内移除 → 强制重排 → 再加回」来重播动画。
  const el = host.value
  if (el) {
    el.classList.remove('is-poked')
    void el.offsetWidth
    el.classList.add('is-poked')
  }
  say(pickLine(current.value, lineN), 1800)
}

/** 登录成功：猫说一句、眨一下眼，跳完再收页。只生效一次。 */
function playIn(ms: number, done: () => void): number {
  const wait = typeof ms === 'number' && ms >= 0 ? ms : 700
  if (going) {
    done()
    return wait
  }
  going = true
  say(pickLine('ok', 0), wait)
  hopTimer = setTimeout(() => {
    hopTimer = null
    done()
  }, wait)
  return wait
}

function onKeydown(e: KeyboardEvent): void {
  if (e.key === 'Enter' || e.key === ' ') {
    e.preventDefault()
    poke()
  }
}

/** 把鼠标坐标换算成视线方向：以两眼连线中点为参考，位移写进 CSS 变量。
 *  只动瞳孔，猫体保持静止——整体跟着动会像整张图在漂。 */
function track(clientX: number, clientY: number): void {
  const el = host.value
  if (!el || current.value === 'ok') return
  const eyes = el.querySelector('.lp-cat-eyes')
  if (!eyes) return
  const r = eyes.getBoundingClientRect()
  if (!r.width || !r.height) return
  const fx = r.left + r.width * EYE_FOCUS.x
  const fy = r.top + r.height * EYE_FOCUS.y
  const s = pupilShift(clientX, clientY, fx, fy, PUPIL_MAX)
  el.style.setProperty('--px', s.x + 'px')
  el.style.setProperty('--py', s.y + 'px')
}

function onMouseMove(e: MouseEvent): void {
  lastEvent = e
  if (queued) return
  queued = true
  raf = window.requestAnimationFrame(() => {
    queued = false
    if (!lastEvent) return
    track(lastEvent.clientX, lastEvent.clientY)
  })
}

/** 鼠标离开窗口：视线回到正中，过渡自然，不突兀。 */
function onLeave(): void {
  const el = host.value
  if (!el) return
  el.style.setProperty('--px', '0px')
  el.style.setProperty('--py', '0px')
}

watch(current, (m) => {
  if (m === 'ok' || m === 'err') host.value?.classList.remove('is-poked')
})

onMounted(() => {
  window.addEventListener('mousemove', onMouseMove, { passive: true })
  document.addEventListener('mouseleave', onLeave)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseleave', onLeave)
  if (sayTimer) clearTimeout(sayTimer)
  if (hopTimer) clearTimeout(hopTimer)
  if (raf) window.cancelAnimationFrame(raf)
})

defineExpose({ say, poke, playIn })
</script>

<template>
  <div
    ref="host"
    class="lp-cat"
    :data-mood="current"
    tabindex="0"
    role="img"
    aria-label="登录页的小猫，点一下会说话"
    @click="poke"
    @keydown="onKeydown"
  >
    <div class="lp-cat-stage">
      <img class="lp-cat-photo" :src="catPhoto" alt="" draggable="false">
      <div class="lp-cat-art" v-html="eyesMarkup"></div>
    </div>
    <div class="cat-say" :class="{ show: bubbleShow }" role="status" aria-live="polite">
      {{ bubbleText }}
    </div>
  </div>
</template>
