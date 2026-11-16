/**
 * 主题偏好：纯逻辑 + 可注入 DOM 的应用函数。
 * 不直接访问 window/localStorage，方便脱离浏览器做静态与运行时验证。
 */

export type ThemeMode = 'light' | 'dark'
export type PresetId = 'blue' | 'mint' | 'violet' | 'coral' | 'rose' | 'cyan' | 'amber' | 'custom'
export type Density = 'standard' | 'comfy' | 'compact'

export interface ThemeState {
  mode: ThemeMode
  preset: PresetId
  accent: string
  density: Density
}

export interface StorageLike {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

/** 键名与旧界面完全一致，保证两套 UI 来回切换时偏好不丢 */
export const KEYS = {
  mode: 'mi-mode',
  preset: 'mi-preset',
  accent: 'mi-accent',
  density: 'mi-density',
  legacyMode: 'mi-theme',
} as const

export const PRESETS: ReadonlyArray<{
  id: Exclude<PresetId, 'custom'>
  name: string
  hex: string
  darkHex: string
}> = [
  { id: 'blue', name: '米家蓝', hex: '#2f6bff', darkHex: '#6d9bff' },
  { id: 'mint', name: '薄荷青', hex: '#0ca678', darkHex: '#38d9a9' },
  { id: 'violet', name: '暮山紫', hex: '#7048e8', darkHex: '#9775fa' },
  { id: 'coral', name: '珊瑚橙', hex: '#f76707', darkHex: '#ff922b' },
  { id: 'rose', name: '玫瑰粉', hex: '#e64980', darkHex: '#faa2c1' },
  { id: 'cyan', name: '晴空青', hex: '#0b7285', darkHex: '#3bc9db' },
  { id: 'amber', name: '琥珀金', hex: '#e8930c', darkHex: '#fcc419' },
]

export const MODES: ReadonlyArray<{ id: ThemeMode; name: string }> = [
  { id: 'light', name: '浅色' },
  { id: 'dark', name: '深色' },
]

export const DENSITIES: ReadonlyArray<{ id: Density; name: string }> = [
  { id: 'standard', name: '标准' },
  { id: 'comfy', name: '宽松' },
  { id: 'compact', name: '紧凑' },
]

export const DEFAULT_THEME: ThemeState = {
  mode: 'light',
  preset: 'blue',
  accent: '',
  density: 'standard',
}

export const ACCENT_RE = /^#[0-9a-fA-F]{6}$/

/** custom 时写在根元素上的全部变量，切换回预设时要逐个清干净 */
export const ACCENT_KEYS = [
  '--tone', '--tone-hover', '--tone-rgb',
  '--blue', '--blue-hover', '--blue-soft', '--focus',
  '--accent', '--accent-strong', '--accent-soft', '--accent-soft-2',
] as const

export function normalizeMode(v: string | null): ThemeMode {
  return v === 'dark' ? 'dark' : 'light'
}

export function normalizePreset(v: string | null): PresetId {
  if (v === 'custom') return 'custom'
  return PRESETS.some((p) => p.id === v) ? (v as PresetId) : DEFAULT_THEME.preset
}

export function normalizeDensity(v: string | null): Density {
  return DENSITIES.some((d) => d.id === v) ? (v as Density) : DEFAULT_THEME.density
}

export function isValidAccent(v: string | null): v is string {
  return typeof v === 'string' && ACCENT_RE.test(v)
}

/**
 * 读偏好。旧版本只写 mi-theme（dark/light），没有 mi-mode；
 * 没有新键时回退到旧键，与旧界面 init() 里的迁移规则一致。
 */
export function readStoredTheme(storage: StorageLike | null): ThemeState {
  if (!storage) return { ...DEFAULT_THEME }
  const accent = storage.getItem(KEYS.accent)
  return {
    mode: normalizeMode(storage.getItem(KEYS.mode) || storage.getItem(KEYS.legacyMode)),
    preset: normalizePreset(storage.getItem(KEYS.preset)),
    accent: isValidAccent(accent) ? accent : '',
    density: normalizeDensity(storage.getItem(KEYS.density)),
  }
}

export function persistTheme(storage: StorageLike | null, s: ThemeState): void {
  if (!storage) return
  storage.setItem(KEYS.mode, s.mode)
  storage.setItem(KEYS.preset, s.preset)
  storage.setItem(KEYS.accent, s.accent)
  storage.setItem(KEYS.density, s.density)
  // 与旧界面互通：旧版读这个键，切回去外观不跳
  storage.setItem(KEYS.legacyMode, s.mode)
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.slice(1)
  return [
    parseInt(h.slice(0, 2), 16),
    parseInt(h.slice(2, 4), 16),
    parseInt(h.slice(4, 6), 16),
  ]
}

function channel(v: number): string {
  return Math.max(0, Math.min(255, Math.round(v))).toString(16).padStart(2, '0')
}

/** 与旧版 applyTheme() 的推导保持一致：浅色掺黑 18%，深色掺白 22% */
function mix(a: string, b: string, ratio: number): string {
  const x = hexToRgb(a)
  const y = hexToRgb(b)
  return '#' + channel(x[0] + (y[0] - x[0]) * ratio)
    + channel(x[1] + (y[1] - x[1]) * ratio)
    + channel(x[2] + (y[2] - x[2]) * ratio)
}

/** 自定义主色现场推导出整套语义变量（预设则由 CSS 规则派生） */
export function deriveAccentVars(hex: string, dark: boolean): Record<string, string> {
  const base = hex.toLowerCase()
  const hover = dark ? mix(base, '#ffffff', 0.22) : mix(base, '#000000', 0.18)
  const [r, g, b] = hexToRgb(base)
  const rgb = `${r} ${g} ${b}`
  return {
    '--tone': base,
    '--tone-hover': hover,
    '--tone-rgb': rgb,
    '--blue': base,
    '--blue-hover': hover,
    '--blue-soft': `rgb(${rgb} / ${dark ? 0.16 : 0.10})`,
    '--focus': `rgb(${rgb} / ${dark ? 0.85 : 0.8})`,
    '--accent': base,
    '--accent-strong': hover,
    '--accent-soft': `rgb(${rgb} / ${dark ? 0.13 : 0.10})`,
    '--accent-soft-2': `rgb(${rgb} / ${dark ? 0.26 : 0.22})`,
  }
}

/** 把偏好涂到根元素。root 由调用方注入，便于测试。 */
export function applyThemeToDocument(root: HTMLElement | null, s: ThemeState): void {
  if (!root) return
  root.dataset.theme = s.mode
  root.dataset.preset = s.preset
  root.dataset.density = s.density
  if (s.preset === 'custom' && isValidAccent(s.accent)) {
    const vars = deriveAccentVars(s.accent, s.mode === 'dark')
    Object.entries(vars).forEach(([k, v]) => root.style.setProperty(k, v))
  } else {
    ACCENT_KEYS.forEach((k) => root.style.removeProperty(k))
  }
}
