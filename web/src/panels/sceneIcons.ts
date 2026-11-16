/* 场景图标：按名称挑一枚最贴近的动作用字形。
 *
 * 线性、24 网格、stroke 1.7——与 devices/icons.ts 同一套画法，
 * 灯 / 窗帘 / 空调直接复用设备图标，避免同一件东西画两遍。
 * 只做「猜一个」：猜不到就用闪电兜底，不为了图标去改场景名。
 */
import { PATHS as DEVICE_PATHS } from '../devices/icons'

const LOCAL: Record<string, string> = {
  home:
    '<path d="M3.6 10.6 12 3.8l8.4 6.8"/>' +
    '<path d="M5.9 9.2V20h12.2V9.2"/>' +
    '<path d="M9.9 20v-5.2h4.2V20"/>',
  away:
    '<path d="M13.2 3.8H19a1.8 1.8 0 0 1 1.8 1.8v12.8A1.8 1.8 0 0 1 19 20.2h-5.8"/>' +
    '<path d="M13.6 8.4 9.2 12l4.4 3.6"/>' +
    '<path d="M4.2 12h8.6"/>',
  moon:
    '<path d="M20.2 14.6A8.6 8.6 0 0 1 9.4 3.8a8.6 8.6 0 1 0 10.8 10.8Z"/>',
  sun:
    '<circle cx="12" cy="12" r="4"/>' +
    '<path d="M12 2.8v2.2"/><path d="M12 19v2.2"/><path d="M2.8 12H5"/>' +
    '<path d="M19 12h2.2"/><path d="M5.4 5.4 7 7"/><path d="M17 17l1.6 1.6"/>' +
    '<path d="M18.6 5.4 17 7"/><path d="M7 17l-1.6 1.6"/>',
  film:
    '<rect x="3.2" y="5" width="17.6" height="14" rx="2.2"/>' +
    '<path d="M10.4 9.4 15 12l-4.6 2.6Z"/>',
  bolt:
    '<path d="M13.2 2.6 5.4 13.6h5.2L9.4 21.4l7.8-11h-5.2Z"/>',
}

const BODY: Record<string, string> = {
  ...DEVICE_PATHS,
  ...LOCAL,
}

/* 顺序有意义：先长词后短词，否则「睡觉灯光」会先被「灯」抢走，
   「离家模式」也会被「家」误判成回家。 */
const RULES: Array<[RegExp, string]> = [
  [/睡|晚安|夜|睡眠/, 'moon'],
  [/起床|早安|晨/, 'sun'],
  [/窗帘|帘/, 'curtain'],
  [/空调|制冷|制热|暖风|新风|冷|热/, 'climate'],
  [/离家|外出|上班|出门|离开/, 'away'],
  [/回家|归来|到家/, 'home'],
  [/影|电影|观影/, 'film'],
  [/灯|照明|亮/, 'light'],
]

export const SCENE_FALLBACK = 'bolt'

/** 名称 → 图标键（可测）。猜不到返回 bolt。 */
export function sceneKind(name: string): string {
  const s = (name || '').trim()
  for (const [re, kind] of RULES) {
    if (re.test(s)) return kind
  }
  return SCENE_FALLBACK
}

/** 返回可直接塞进 v-html 的 <svg>；根写死 fill="none"，否则会被主题染成实心。 */
export function sceneIcon(name: string): string {
  const body = BODY[sceneKind(name)] || BODY[SCENE_FALLBACK]
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'
    + ' aria-hidden="true" focusable="false">' + body + '</svg>'
}
