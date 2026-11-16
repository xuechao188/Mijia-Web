/* Vue 版登录猫的纯逻辑层。
 *
 * 猫体是一张 3D 渲染位图（assets/cat-orange.webp），眼睛长在图上，所以这里
 * 只保留与位图对齐的几何常量、四态台词与瞳孔跟随算法。旧界面
 * static/login_cat.js 仍是手绘 SVG 面包猫，两者互不影响；
 * tests/test_vue_login.py 继续交叉校验 MOODS / LINES / moodOf / pupilShift。
 */

export type Mood = 'idle' | 'wait' | 'ok' | 'err'

export const MOODS: readonly Mood[] = ['idle', 'wait', 'ok', 'err'] as const

export const LINES: Record<Mood, readonly string[]> = {
  idle: ['喵', '我在呢', '慢慢来，不着急', '今天想看哪台设备', '橘猫已就位'],
  wait: ['扫一下就好', '我盯着二维码呢', '手机在手上吗', '别急，我等你'],
  ok: ['喵！进去啦', '欢迎回来', '门开着呢'],
  err: ['唔…码过期了', '再来一次吧', '这次没扫上'],
}

/** 二维码状态文案 → 猫的心情。与旧版 moodOf 同判据。 */
export function moodOf(text: string | null | undefined, cls?: string): Mood {
  const t = String(text == null ? '' : text)
  if (cls === 'ok') return 'ok'
  if (cls === 'err') return 'err'
  if (t.indexOf('成功') >= 0) return 'ok'
  if (t.indexOf('过期') >= 0 || t.indexOf('失败') >= 0 || t.indexOf('出错') >= 0) return 'err'
  if (t.indexOf('扫码') >= 0) return 'wait'
  return 'idle'
}

/** 瞳孔跟随：只取前 6 倍半径的信号，远处封顶，不会顶出眼白。 */
export function pupilShift(
  mx: number, my: number, cx: number, cy: number, max = 2.4,
): { x: number; y: number } {
  const m = typeof max === 'number' && max > 0 ? max : 2.4
  const dx = Number(mx) - Number(cx)
  const dy = Number(my) - Number(cy)
  if (!isFinite(dx) || !isFinite(dy)) return { x: 0, y: 0 }
  const d = Math.sqrt(dx * dx + dy * dy)
  if (!d) return { x: 0, y: 0 }
  const k = Math.min(1, d / 220)
  const r = Math.min(m, d * k * 0.12)
  return {
    x: Math.round((dx / d) * r * 100) / 100,
    y: Math.round((dy / d) * r * 100) / 100,
  }
}

export function pickLine(mood: Mood, n: number): string {
  const list = LINES[mood] || LINES.idle
  const i = Math.abs(parseInt(String(n), 10) || 0) % list.length
  return list[i]
}

/* ---------------------------------------------------------------- 位图对齐
 * 橘猫图 664×860（webp 与 SVG 覆盖层共用同一 viewBox）。
 * 眼球用「由内向外找第一处暗环」的方式测得虹膜可见半径，
 * 暗环本身留给位图当眼线，覆盖层只画到虹膜外沿。
 */
export const CAT_VIEW = { w: 664, h: 860 } as const

export interface CatEye { cx: number; cy: number; r: number }

/** 左、右眼球：中心与虹膜可见半径。 */
export const CAT_EYES: readonly CatEye[] = [
  { cx: 211.91, cy: 237.97, r: 39.05 },
  { cx: 395.85, cy: 235.55, r: 39.28 },
] as const

/** 两眼中心的中点占整图比例，供组件把鼠标坐标换算成视线方向。 */
export const EYE_FOCUS = {
  x: (CAT_EYES[0].cx + CAT_EYES[1].cx) / 2 / CAT_VIEW.w,
  y: (CAT_EYES[0].cy + CAT_EYES[1].cy) / 2 / CAT_VIEW.h,
} as const

/** 瞳孔横竖半径占虹膜半径的比例：略小于位图原瞳孔，留出移动余量。 */
export const PUPIL_RX = 0.68
export const PUPIL_RY = 0.70

/** 瞳孔最大偏移（用户单位）：虹膜 39，瞳孔 26.5，留 1.0 的边不穿帮。 */
export const PUPIL_MAX = 11.6

/** 左/右眼皮三段色（取自眼上毛色，上暗下亮），眨眼遮罩用它贴合毛皮。 */
export const LID_TONE = [
  ['#bd8e5c', '#a97a4b', '#95643a'],
  ['#bb9673', '#a9886b', '#94673f'],
] as const

const f2 = (n: number): number => Math.round(n * 100) / 100

/** 眼睑帘：毛色填充 + 弯曲下沿 + 睫线。depth 是占虹膜直径的比例。 */
function droop(i: number, cx: number, cy: number, r: number, depth: number, tag: string): string {
  const top = cy - r
  const v = r * depth
  return '<g class="cat-droop cat-droop-' + tag + '">' +
    '<path fill="url(#cat-lid-grad-' + i + ')" d="M' + f2(cx - r) + ' ' + f2(top) +
      'h' + f2(r * 2) + 'v' + f2(v) +
      'q' + f2(-r) + ' ' + f2(r * 0.30) + ' ' + f2(-r * 2) + ' 0z"/>' +
    '<path class="cat-droop-edge" d="M' + f2(cx + r) + ' ' + f2(top + v) +
      'q' + f2(-r) + ' ' + f2(r * 0.30) + ' ' + f2(-r * 2) + ' 0"' +
      ' stroke-width="' + f2(r * 0.075) + '"/>' +
  '</g>'
}

/** 静态覆盖层：虹膜、纤维、瞳孔、高光、眼皮。只有眼珠是活的，猫体是位图。 */
export function eyeOverlay(): string {
  const eye = (e: CatEye, i: number): string => {
    const id = 'e' + i
    const r = e.r
    const cx = e.cx
    const cy = e.cy

    // 虹膜纤维：18 条极淡的放射纹，补上平面渐变缺的细节
    let fibers = ''
    for (let k = 0; k < 18; k++) {
      const a = ((k * 20 + 7) * Math.PI) / 180
      const c = Math.cos(a)
      const s = Math.sin(a)
      fibers += '<line x1="' + f2(cx + c * r * 0.42) + '" y1="' + f2(cy + s * r * 0.42) +
        '" x2="' + f2(cx + c * r * 0.965) + '" y2="' + f2(cy + s * r * 0.965) +
        '" stroke="#4a2a04" stroke-width="' + f2(r * 0.035) +
        '" stroke-opacity="' + (0.12 + (k % 3) * 0.035).toFixed(3) +
        '" stroke-linecap="round"/>'
    }

    const prx = f2(r * PUPIL_RX)
    const pry = f2(r * PUPIL_RY)

    return '' +
      '<g class="cat-eye cat-eye-' + i + '">' +
        '<clipPath id="cat-clip-' + id + '"><circle cx="' + cx + '" cy="' + cy + '" r="' + r + '"/></clipPath>' +
        '<g clip-path="url(#cat-clip-' + id + ')">' +
          // 虹膜底色：中心偏亮的琥珀，边缘压暗
          '<circle class="cat-iris" cx="' + cx + '" cy="' + cy + '" r="' + r + '"/>' +
          '<g class="cat-fibers">' + fibers + '</g>' +
          // 角膜缘环：压一圈深褐，让眼球边缘沉下去
          '<circle class="cat-limbal" cx="' + cx + '" cy="' + cy + '" r="' + f2(r * 0.945) +
            '" stroke-width="' + f2(r * 0.1) + '"/>' +
          // 瞳孔外沿的亮环：真猫虹膜贴近瞳孔处更亮，眼睛才有神
          '<circle class="cat-halo" cx="' + cx + '" cy="' + cy + '" r="' + f2(r * 0.80) +
            '" stroke-width="' + f2(r * 0.075) + '"/>' +
          // 瞳孔：跟随 --px/--py 平移，竖椭圆带柔边
          '<g class="cat-pupil">' +
            '<ellipse class="cat-pupil-body" cx="' + cx + '" cy="' + cy +
              '" rx="' + prx + '" ry="' + pry + '"/>' +
            '<ellipse class="cat-glint" cx="' + f2(cx - r * 0.30) + '" cy="' + f2(cy - r * 0.36) +
              '" rx="' + f2(r * 0.20) + '" ry="' + f2(r * 0.145) +
              '" transform="rotate(-22 ' + f2(cx - r * 0.30) + ' ' + f2(cy - r * 0.36) + ')"/>' +
            '<circle class="cat-glint sm" cx="' + f2(cx + r * 0.27) + '" cy="' + f2(cy + r * 0.28) +
              '" r="' + f2(r * 0.075) + '"/>' +
          '</g>' +
          // 下眼睑水光：一道很淡的弧，给眼球添点湿感
          '<path class="cat-wet" d="M' + f2(cx - r * 0.6) + ' ' + f2(cy + r * 0.34) +
            'q' + f2(r * 0.6) + ' ' + f2(r * 0.44) + ' ' + f2(r * 1.2) + ' 0"' +
            ' stroke-width="' + f2(r * 0.07) + '"/>' +
          // 眼睑：两条固定深度的毛色帘（深度不同、各自受四态控制）。
          // 用 scaleY 缩放会受 SVG 变换原点影响，缩到画布外，所以直接画两条。
          droop(i, cx, cy, r, 0.70, 'deep') +
          droop(i, cx, cy, r, 0.44, 'soft') +
          // 上眼皮：眨眼时落下；颜色取自该侧眼上毛皮，写进 fill 免得 CSS 二次维护
          '<path class="cat-lid" fill="url(#cat-lid-grad-' + i + ')" d="M' + f2(cx - r) + ' ' + f2(cy - r) +
            'h' + f2(r * 2) + 'v' + f2(r * 2) + 'h' + f2(-r * 2) + 'z"/>' +
        '</g>' +
      '</g>'
  }
  return '' +
    '<svg class="lp-cat-eyes" viewBox="0 0 ' + CAT_VIEW.w + ' ' + CAT_VIEW.h + '" ' +
      'fill="none" aria-hidden="true" focusable="false">' +
      '<defs>' +
        // 虹膜渐变：色值取自位图虹膜分层采样，接缝处与原始毛色一致
        '<radialGradient id="cat-iris-grad" cx="46%" cy="36%" r="64%">' +
          '<stop offset="0%" stop-color="#c08214"/>' +
          '<stop offset="58%" stop-color="#b8740e"/>' +
          '<stop offset="80%" stop-color="#a5660b"/>' +
          '<stop offset="93%" stop-color="#8a550f"/>' +
          '<stop offset="100%" stop-color="#6f4110"/>' +
        '</radialGradient>' +
        // 眼皮：上暗下亮的竖向渐变，落下时不像贴片
        LID_TONE.map((t, i) =>
          '<linearGradient id="cat-lid-grad-' + i + '" x1="0" y1="0" x2="0" y2="1">' +
            '<stop offset="0%" stop-color="' + t[0] + '"/>' +
            '<stop offset="58%" stop-color="' + t[1] + '"/>' +
            '<stop offset="100%" stop-color="' + t[2] + '"/>' +
          '</linearGradient>').join('') +
        // 瞳孔：中心实、边缘化开，避免贴纸感
        '<radialGradient id="cat-pupil-grad" cx="50%" cy="50%" r="50%">' +
          '<stop offset="0%" stop-color="#0a0806" stop-opacity="1"/>' +
          '<stop offset="72%" stop-color="#0d0a07" stop-opacity="1"/>' +
          '<stop offset="100%" stop-color="#241809" stop-opacity="0"/>' +
        '</radialGradient>' +
      '</defs>' +
      eye(CAT_EYES[0], 0) +
      eye(CAT_EYES[1], 1) +
    '</svg>'
}
