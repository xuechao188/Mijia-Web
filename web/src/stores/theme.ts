import { computed, ref, watch } from 'vue'
import { defineStore } from 'pinia'
import {
  ACCENT_RE,
  DEFAULT_THEME,
  applyThemeToDocument,
  persistTheme,
  readStoredTheme,
  normalizeDensity,
  normalizeMode,
  type Density,
  type PresetId,
  type StorageLike,
  type ThemeMode,
  type ThemeState,
} from '../theme/core'

function storage(): StorageLike | null {
  try {
    return typeof localStorage === 'undefined' ? null : localStorage
  } catch {
    return null
  }
}

export const useThemeStore = defineStore('theme', () => {
  const saved = readStoredTheme(storage())
  const mode = ref<ThemeMode>(saved.mode)
  const preset = ref<PresetId>(saved.preset)
  const accent = ref<string>(saved.accent)
  const density = ref<Density>(saved.density)

  const state = computed<ThemeState>(() => ({
    mode: mode.value,
    preset: preset.value,
    accent: accent.value,
    density: density.value,
  }))

  const isCustom = computed(() => preset.value === 'custom')

  function apply(): void {
    applyThemeToDocument(
      typeof document === 'undefined' ? null : document.documentElement,
      state.value,
    )
    persistTheme(storage(), state.value)
  }

  function setMode(v: ThemeMode): void { mode.value = normalizeMode(v) }
  function toggleMode(): void { mode.value = mode.value === 'dark' ? 'light' : 'dark' }
  function setPreset(v: PresetId): void { preset.value = v }
  function setDensity(v: Density): void { density.value = normalizeDensity(v) }
  function setAccent(hex: string): void {
    if (!ACCENT_RE.test(hex)) return
    accent.value = hex
    preset.value = 'custom'
  }
  function reset(): void {
    mode.value = DEFAULT_THEME.mode
    preset.value = DEFAULT_THEME.preset
    accent.value = DEFAULT_THEME.accent
    density.value = DEFAULT_THEME.density
  }

  // 首帧也要应用一次：内联脚本只预涂了 data-*，custom 主色的
  // 推导变量与 localStorage 回写由这里补齐。
  apply()
  // 任一偏好变化都立刻落到根元素 + localStorage
  watch(state, apply)

  return {
    mode, preset, accent, density, state, isCustom,
    setMode, toggleMode, setPreset, setAccent, setDensity, reset, apply,
  }
})
