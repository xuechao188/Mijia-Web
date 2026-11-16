<script setup lang="ts">
/* 取流失败弹窗。
 *
 * 只在点了「获取实时画面」而画面出不来时出现，把「为什么播不了」一次讲完：
 * 结论、原因、条件、原始返回，然后关掉。抽屉里不再常驻任何状态条 —— 大多数
 * 时候用户并不看实时画面，那条横幅只是白占版面。
 *
 * 关闭后组件保留最后一帧内容（cache），避免离场动画期间文案被清空闪一下。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { capDialog, RAW_SUMMARY, type CamTip } from '../devices/camera'
import { dialogEnter, dialogLeave } from '../motion'

const props = defineProps<{ tip: CamTip | null; busy?: boolean }>()
const emit = defineEmits<{ close: []; retry: [] }>()

const cache = ref<CamTip | null>(props.tip)
const open = ref(!!props.tip)

watch(() => props.tip, (v) => {
  if (v) cache.value = v
  open.value = !!v
}, { immediate: true })

const v = computed(() => capDialog(cache.value?.cap, cache.value?.note))

function onEnter(el: Element): void { dialogEnter(el) }
function onLeave(el: Element, done: () => void): void { dialogLeave(el, done) }
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && open.value) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <Transition :css="false" @enter="onEnter" @leave="onLeave">
    <div v-if="open" class="cap-layer" role="dialog" aria-modal="true" :aria-label="v.title">
      <div class="cap-mask" @click="emit('close')"></div>
      <div class="cap-box m-glass m-glass-strong" :class="'is-' + v.tone">
        <header class="cap-head">
          <span class="cap-dot" aria-hidden="true"></span>
          <h4>{{ v.title }}</h4>
          <span v-if="v.vendor" class="cap-tag">{{ v.vendor }}</span>
          <button type="button" class="icon-btn cap-x" aria-label="关闭" @click="emit('close')">
            <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </header>

        <div class="cap-body">
          <p v-if="v.reason">{{ v.reason }}</p>
          <p v-if="v.advice">{{ v.advice }}</p>
          <p v-if="v.note" class="cap-fallback">{{ v.note }}</p>
          <details v-if="cache?.rawText" class="cam-raw">
            <summary>{{ RAW_SUMMARY }}</summary>
            <pre>{{ cache.rawText }}</pre>
          </details>
        </div>

        <footer class="cap-foot">
          <button type="button" class="btn sm ghost" :disabled="busy" @click="emit('retry')">
            {{ busy ? '正在检测…' : v.action }}
          </button>
          <button type="button" class="btn sm" @click="emit('close')">知道了</button>
        </footer>
      </div>
    </div>
  </Transition>
</template>
