<script setup lang="ts">
/* 手动场景：与旧界面 #scene-panel 同源，点一下执行，结果只 toast + 刷事件流。
 * 每个场景是一块「砖」：线性图标 + 名称；同名场景补一个序号角标。
 * 按下有水波、执行中转圈、成功轻震一下——三段都由 motion/ 统一给。 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { SCENE_EMPTY, dupeIndex, sceneLabel } from '../panels/scenes'
import { sceneIcon } from '../panels/sceneIcons'
import { scenePress, sceneSettle, spin, spinEdge } from '../motion'
import { usePanelsStore } from '../stores/panels'
import type { SceneItem } from '../panels/types'

const store = usePanelsStore()

/* 只按当前家庭渲染场景（切家庭后自动更新），与自动化同一口径。 */
const scenes = computed(() => store.scopedScenes)
const dupes = computed(() => dupeIndex(scenes.value))
const rowEl = ref<HTMLElement | null>(null)

function busy(id: string): boolean { return Boolean(store.sceneBusy[id]) }

/* 转圈交给动效层：CSS 里不写 infinite，减弱动效时自然停住。
   busy 只由 store 决定，所以盯 store 而不是盯点击。 */
watch(() => store.sceneBusy, () => {
  void nextTick(() => {
    rowEl.value?.querySelectorAll<HTMLElement>('.scene-tile').forEach((tile) => {
      const on = tile.classList.contains('is-busy')
      spin(tile.querySelector('.st-spin'), on)
      spinEdge(tile.querySelector('.cb-edge'), on)
    })
  })
})

onBeforeUnmount(() => {
  rowEl.value?.querySelectorAll<HTMLElement>('.st-spin').forEach((el) => spin(el, false))
  rowEl.value?.querySelectorAll<HTMLElement>('.cb-edge').forEach((el) => spinEdge(el, false))
})

function onDown(s: SceneItem, e: PointerEvent): void {
  const el = e.currentTarget as HTMLElement
  if (!el || busy(s.scene_id)) return
  const r = el.getBoundingClientRect()
  scenePress(el, e.clientX - r.left, e.clientY - r.top)
}

async function run(s: SceneItem, e: MouseEvent): Promise<void> {
  if (busy(s.scene_id)) return
  const el = e.currentTarget as HTMLElement
  const ok = await store.runScene(s)
  if (ok) sceneSettle(el)
}
</script>

<template>
  <section class="scene-panel m-surface">
    <div class="dr-history-head">
      <span class="dr-h-label">场景</span>
      <span class="dim-note mono">{{ scenes.length }} 个</span>
    </div>
    <div v-if="!scenes.length" class="dim-note scene-empty">{{ SCENE_EMPTY }}</div>
    <div v-else ref="rowEl" class="scene-row">
      <button v-for="s in scenes" :key="s.scene_id" type="button"
              class="btn scene-btn scene-tile" :class="{ 'is-busy': busy(s.scene_id) }"
              :disabled="busy(s.scene_id)"
              :aria-label="'执行场景 ' + sceneLabel(s)"
              @pointerdown="onDown(s, $event)"
              @click="run(s, $event)">
        <span class="cb-edge" aria-hidden="true"></span>
        <span class="st-ico" v-html="sceneIcon(sceneLabel(s))"></span>
        <span class="st-text">
          <span class="st-name">{{ sceneLabel(s) }}</span>
          <span v-if="dupes[s.scene_id]" class="st-dupe mono">×{{ dupes[s.scene_id] }}</span>
        </span>
        <span class="st-go" aria-hidden="true">
          <svg class="st-arrow" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4.8 12h13.4" /><path d="M13.2 7l5 5-5 5" />
          </svg>
          <span class="st-spin"></span>
        </span>
      </button>
    </div>
  </section>
</template>
