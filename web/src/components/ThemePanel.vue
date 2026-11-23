<script setup lang="ts">
import { computed } from 'vue'
import { ACCENT_RE, BACKGROUNDS, DENSITIES, MODES, PRESETS } from '../theme/core'
import { useThemeStore } from '../stores/theme'

const theme = useThemeStore()
const pickerValue = computed({
  get: () => (ACCENT_RE.test(theme.accent) ? theme.accent : '#236de9'),
  set: (v: string) => theme.setAccent(v),
})
const solidBackgrounds = BACKGROUNDS.filter((b) => b.id !== 'ambient')
const isSolid = computed(() => theme.background !== 'ambient')
</script>

<template>
  <aside class="tp m-glass-menu">
    <div class="tp-head">
      <span class="section-label">外观设置</span>
      <button class="tp-reset" @click="theme.reset()">恢复默认</button>
    </div>

    <div class="tp-row">
      <span class="tp-key">模式</span>
      <div class="tp-seg m-groove">
        <button v-for="m in MODES" :key="m.id" class="tp-seg-btn"
                :class="{ 'is-active': theme.mode === m.id }"
                @click="theme.setMode(m.id)">{{ m.name }}</button>
      </div>
    </div>

    <div class="tp-row">
      <span class="tp-key">主色</span>
      <div class="tp-swatches">
        <button v-for="p in PRESETS" :key="p.id" class="tp-swatch"
                :class="{ 'is-active': theme.preset === p.id }"
                :style="{ '--swatch': p.hex }"
                :title="p.name" :aria-label="p.name"
                @click="theme.setPreset(p.id)"></button>
        <label class="tp-custom" :class="{ 'is-active': theme.isCustom }" title="自定义主色">
          <input v-model="pickerValue" type="color" aria-label="自定义主色">
        </label>
      </div>
    </div>

    <div class="tp-row">
      <span class="tp-key">背景</span>
      <div class="tp-seg m-groove">
        <button class="tp-seg-btn" :class="{ 'is-active': !isSolid }"
                @click="theme.setBackground('ambient')">氛围</button>
        <button class="tp-seg-btn" :class="{ 'is-active': isSolid }"
                @click="theme.setBackground(isSolid ? theme.background : 'chalk')">纯色</button>
      </div>
    </div>

    <div v-if="isSolid" class="tp-row tp-bg-row">
      <span class="tp-key">底色</span>
      <div class="tp-swatches">
        <button v-for="b in solidBackgrounds" :key="b.id" class="tp-swatch"
                :class="{ 'is-active': theme.background === b.id }"
                :style="{ '--swatch': b.swatch }"
                :title="b.name" :aria-label="b.name"
                @click="theme.setBackground(b.id)"></button>
      </div>
    </div>

    <div class="tp-row">
      <span class="tp-key">密度</span>
      <div class="tp-seg m-groove">
        <button v-for="d in DENSITIES" :key="d.id" class="tp-seg-btn"
                :class="{ 'is-active': theme.density === d.id }"
                @click="theme.setDensity(d.id)">{{ d.name }}</button>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.tp {
  padding: 22px 24px 20px;
  border-radius: var(--r-lg);
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.tp-head { display: flex; align-items: center; justify-content: space-between; }
.tp-reset {
  font-size: 12px;
  color: var(--ink-soft);
  padding: 5px 10px;
  border-radius: var(--r-xs);
}
.tp-reset:hover { color: var(--blue); background: var(--hover-bg); }
.tp-row { display: flex; align-items: center; gap: 14px; }
.tp-key { flex: 0 0 34px; font-size: 12px; color: var(--ink-muted); }
.tp-seg {
  display: inline-flex;
  gap: 3px;
  padding: 3px;
  border-radius: 999px;
}
.tp-seg-btn {
  min-width: 54px;
  height: var(--control-h-sm);
  padding: 0 12px;
  border-radius: 999px;
  font-size: 12px;
  color: var(--ink-muted);
  transition: color .18s, background .18s, box-shadow .18s;
}
.tp-seg-btn.is-active {
  background: var(--blue-soft);
  box-shadow: inset 0 0 0 1px rgb(var(--tone-rgb) / .35), var(--e-color-1);
  color: var(--blue);
  font-weight: 600;
}
.tp-swatches { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.tp-swatch {
  width: 22px; height: 22px;
  border-radius: 999px;
  background: var(--swatch);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .08), var(--e1);
  transition: transform .18s var(--ease-premium), box-shadow .18s;
}
.tp-swatch:hover { transform: scale(1.12); }
.tp-swatch.is-active { box-shadow: 0 0 0 2px var(--surface-solid), 0 0 0 4px var(--swatch), var(--e1); }
.tp-custom {
  position: relative;
  width: 22px; height: 22px;
  border-radius: 999px;
  overflow: hidden;
  cursor: pointer;
  background: conic-gradient(#f05a50, #e8b90c, #58a021, #236de9, #7048e8, #f05a50);
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .08);
}
.tp-custom.is-active { box-shadow: 0 0 0 2px var(--surface-solid), 0 0 0 4px var(--blue), var(--e1); }
.tp-custom input { position: absolute; inset: -8px; width: 40px; height: 40px; opacity: 0; cursor: pointer; }
/* 纯色底色偏浅，加一圈发丝描边保证在面板上可辨；选中态用主色双环 */
.tp-bg-row .tp-swatch { box-shadow: inset 0 0 0 1px rgba(0, 0, 0, .16), var(--e1); }
.tp-bg-row .tp-swatch.is-active { box-shadow: 0 0 0 2px var(--surface-solid), 0 0 0 4px var(--blue), var(--e1); }
</style>
