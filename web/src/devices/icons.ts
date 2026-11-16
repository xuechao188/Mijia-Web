/* 设备类型图标：13 个类别各一枚线性图标。
 *
 * 与 static/device_icons.js 的 PATHS / svg() 逐字同源，测试会逐类比对。
 * 颜色不写在这里——统一交给 CSS 的 --cat 变量，改主题色只动一处。
 * svg 根必须写死 fill="none"：pico 系样式里有 svg:not([fill]){fill:currentColor}，
 * 一旦被染成实色，图标就会糊成一团。
 */
import type { Category } from './types'

export const PATHS: Record<string, string> = {
  light:
    '<path d="M12 3.2a5.8 5.8 0 0 0-3.4 10.5c.5.4.8 1 .8 1.6v.9h5.2v-.9c0-.6.3-1.2.8-1.6A5.8 5.8 0 0 0 12 3.2Z"/>' +
    '<path d="M9.6 18.6h4.8"/><path d="M10.4 21h3.2"/>',
  'climate-sensor':
    '<path d="M12 3.4a2 2 0 0 0-2 2v7.2a4.6 4.6 0 1 0 4 0V5.4a2 2 0 0 0-2-2Z"/>' +
    '<path d="M12 9.4v6.2"/><circle cx="12" cy="17.2" r="1.5"/>',
  climate:
    '<rect x="2.8" y="4.6" width="18.4" height="6.8" rx="2"/>' +
    '<path d="M6.6 8h.01"/>' +
    '<path d="M6.4 14.4c1.1 0 1.7 1.4 2.8 1.4s1.7-1.4 2.8-1.4 1.7 1.4 2.8 1.4 1.7-1.4 2.8-1.4"/>',
  appliance:
    '<path d="M4.2 10.4h15.6v3.3a5.4 5.4 0 0 1-5.4 5.4H9.6a5.4 5.4 0 0 1-5.4-5.4v-3.3Z"/>' +
    '<path d="M2.6 10.4h18.8"/>' +
    '<path d="M9.2 6.9c0-1 1-1.3 1-2.3"/><path d="M13.2 6.9c0-1 1-1.3 1-2.3"/>',
  purifier:
    '<path d="M3.6 8.2h10.2a2.9 2.9 0 1 0-2.9-2.9"/>' +
    '<path d="M3.6 12.2h13.4a2.9 2.9 0 1 1-2.9 2.9"/>' +
    '<path d="M3.6 16.2h6.6"/>',
  cleaner:
    '<circle cx="12" cy="12.8" r="7.4"/><circle cx="12" cy="12.8" r="2.6"/>' +
    '<path d="M12 5.4V3.2"/>',
  camera:
    '<path d="M3 8.6A2.4 2.4 0 0 1 5.4 6.2h1.5l1.3-1.8h7.6l1.3 1.8h1.5A2.4 2.4 0 0 1 21 8.6v8a2.4 2.4 0 0 1-2.4 2.4H5.4A2.4 2.4 0 0 1 3 16.6Z"/>' +
    '<circle cx="12" cy="12.6" r="3.4"/>',
  curtain:
    '<path d="M3 3.6h18"/><path d="M6.8 3.6v16.2"/><path d="M17.2 3.6v16.2"/>' +
    '<path d="M6.8 19.8c1.9-.9 2.8-3.1 2.8-6.2V3.6"/>' +
    '<path d="M17.2 19.8c-1.9-.9-2.8-3.1-2.8-6.2V3.6"/>',
  outlet:
    '<path d="M9 3.2v4.4"/><path d="M15 3.2v4.4"/>' +
    '<path d="M6.2 7.6h11.6v4.3a5.8 5.8 0 0 1-11.6 0Z"/>' +
    '<path d="M12 17.7v3.2"/>',
  switch:
    '<rect x="2.8" y="7.2" width="18.4" height="9.6" rx="4.8"/>' +
    '<circle cx="16.4" cy="12" r="2.5"/>',
  sensor:
    '<circle cx="12" cy="12" r="1.5"/>' +
    '<path d="M8.9 8.9a4.4 4.4 0 0 0 0 6.2"/><path d="M15.1 15.1a4.4 4.4 0 0 0 0-6.2"/>' +
    '<path d="M6 6a8.5 8.5 0 0 0 0 12"/><path d="M18 18a8.5 8.5 0 0 0 0-12"/>',
  hub:
    '<rect x="2.8" y="13.2" width="18.4" height="6.6" rx="2"/>' +
    '<path d="M6.8 13.2v-2.6"/><path d="M17.2 13.2v-2.6"/>' +
    '<path d="M6.8 10.6 5 7"/><path d="M17.2 10.6 19 7"/>' +
    '<path d="M6.2 16.5h.01"/><path d="M9.6 16.5h3.2"/>',
  ir:
    '<rect x="6.8" y="2.6" width="10.4" height="18.8" rx="3"/>' +
    '<circle cx="12" cy="6.8" r="1.6"/>' +
    '<path d="M9.6 11.6h4.8"/><path d="M9.6 14.4h4.8"/>' +
    '<path d="M9.6 17.2h2.6"/>',
  generic:
    '<path d="M12 3 4.2 7v10L12 21l7.8-4V7Z"/>' +
    '<path d="M4.2 7 12 11l7.8-4"/><path d="M12 11v10"/>',
}

export const CATS: Category[] = Object.keys(PATHS) as Category[]

/** 返回可直接塞进 v-html 的 <svg> 字符串；未知类别退回通用图标。 */
export function svg(cat: string): string {
  const body = PATHS[cat] || PATHS.generic
  return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"'
    + ' aria-hidden="true" focusable="false">' + body + '</svg>'
}

export function has(cat: string): boolean {
  return Object.prototype.hasOwnProperty.call(PATHS, cat)
}
