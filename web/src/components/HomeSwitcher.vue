<script setup lang="ts">
/* 左上角品牌右侧的家庭显示与切换（米家 App 顶部「我的家」加下拉箭头）。
 *
 * 层级分工：这里只切家庭，房间交给左侧列表。切家庭后视图落到该家庭的
 * 全部设备，房间列表随之重算，因此两处不会出现「家庭 A / 房间 ∈ B」。
 */
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useDevicesStore } from '../stores/devices'

const store = useDevicesStore()
const open = ref(false)
const root = ref<HTMLElement | null>(null)

const current = computed(() => store.activeHome?.name || '未分配')
const items = computed(() => store.homes.map((h) => ({
  name: h.name, count: h.dids.length,
})))

function toggle(): void { open.value = !open.value }
function pick(name: string): void {
  store.setHome(name)
  open.value = false
}

function onDocPointer(e: PointerEvent): void {
  if (!open.value) return
  if (root.value && !root.value.contains(e.target as Node)) open.value = false
}
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('pointerdown', onDocPointer)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointer)
  document.removeEventListener('keydown', onKey)
})
</script>

<template>
  <div ref="root" class="hs">
    <button class="hs-btn" type="button" aria-haspopup="listbox" :aria-expanded="open"
            :title="'当前家庭：' + current" @click="toggle">
      <span class="hs-name">{{ current }}</span>
      <svg class="ui-ico hs-caret" viewBox="0 0 16 16" aria-hidden="true">
        <path d="m4.6 6.4 3.4 3.4 3.4-3.4" />
      </svg>
    </button>

    <div v-if="open" class="hs-menu m-glass-menu" role="listbox" aria-label="切换家庭">
      <div class="hs-sec">家庭</div>
      <button v-for="h in items" :key="h.name" type="button" role="option"
              :aria-selected="store.activeHome?.name === h.name"
              class="hs-item" :class="{ active: store.activeHome?.name === h.name }"
              @click="pick(h.name)">
        <span class="hs-label" :title="h.name">{{ h.name }}</span>
        <span class="hs-n mono">{{ h.count }}</span>
      </button>
    </div>
  </div>
</template>
