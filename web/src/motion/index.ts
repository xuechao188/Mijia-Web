/* 动效层唯一入口：所有 GSAP 调用都从这里出去。
 *
 * 组件只 import 语义函数（pageEnter / releaseCards / drawerEnter / …），
 * 不直接碰 gsap，也不写时长。好处是节奏能被一处改掉，而且
 * prefers-reduced-motion 只需要在这一个文件里判断 —— 关掉动效时
 * 每个函数都直接进终态，不靠 CSS 兜底。
 */
import gsap from 'gsap'
import { VOICE } from './voice'

export { VOICE } from './voice'

type Tween = ReturnType<typeof gsap.to>

let reduced = false
if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)')
  reduced = mq.matches
  const sync = (e: MediaQueryListEvent): void => { reduced = e.matches }
  if (typeof mq.addEventListener === 'function') mq.addEventListener('change', sync)
  else if (typeof mq.addListener === 'function') mq.addListener(sync)
}

/** 系统要求减弱动效，或当前没有 DOM（Node 探针）时，全部动效关闭。 */
export function motionOff(): boolean {
  return reduced || typeof document === 'undefined'
}

/** 给 Vue <Transition :css="false"> 的 done 加一道保险：动画回调没来也能收尾。 */
function finish(done: () => void, dur: number): () => void {
  let fired = false
  const fin = (): void => {
    if (fired) return
    fired = true
    done()
  }
  if (typeof setTimeout === 'function') setTimeout(fin, Math.round(dur * 1000) + 180)
  return fin
}

/* ── 导：主标签页切换 ─────────────────────────────────────────── */
export function pageEnter(el: Element, done: () => void): void {
  if (motionOff()) { done(); return }
  const v = VOICE.guide
  gsap.fromTo(el, { opacity: 0, y: v.rise },
    {
      opacity: 1, y: 0, duration: v.dur, ease: v.ease,
      onComplete: finish(done, v.dur), clearProps: 'opacity,transform',
    })
}

export function pageLeave(el: Element, done: () => void): void {
  if (motionOff()) { done(); return }
  const dur = VOICE.guide.dur * 0.72
  gsap.to(el, {
    opacity: 0, y: -VOICE.guide.rise * 0.6, duration: dur, ease: 'power1.in',
    onComplete: finish(done, dur),
  })
}

/* ── 放：卡片入场，错峰 18ms ─────────────────────────────────── */
const CARD_SEL = '.device-card, [data-widget="weather"]'

/** 只给还没入场的元素播；replay 时清掉标记重播（切家庭 / 换筛选）。 */
export function releaseCards(root: HTMLElement | null, opts: { replay?: boolean } = {}): void {
  if (!root) return
  const all = Array.from(root.querySelectorAll<HTMLElement>(CARD_SEL))
  if (!all.length) return
  if (opts.replay) all.forEach((el) => { delete el.dataset.motionIn })
  const fresh = all.filter((el) => el.dataset.motionIn !== '1')
  if (!fresh.length) return
  fresh.forEach((el) => { el.dataset.motionIn = '1' })
  if (motionOff()) return
  const v = VOICE.release
  gsap.fromTo(fresh, { opacity: 0, y: v.rise, scale: v.scale },
    {
      opacity: 1, y: 0, scale: 1, duration: v.dur, ease: v.ease, stagger: v.stagger,
      clearProps: 'opacity,transform',
    })
}

/* ── 放：弹框入场 / 收起（居中弹出，位移小、靠透明度与微缩放） ──
 * 旧的右侧抽屉是 x 轴滑入；改成居中弹框后原地方向没有意义，
 * 改成 y 轴 12px 抬升 + 0.985 缩放，视线落在中心时最轻。 */
export function drawerEnter(layer: Element | null): void {
  if (!layer || motionOff()) return
  const mask = layer.querySelector('.drawer-mask')
  const panel = layer.querySelector('.sheet')
  const v = VOICE.release
  if (mask) gsap.fromTo(mask, { opacity: 0 }, { opacity: 1, duration: v.dur * 0.6, ease: 'power2.out' })
  if (panel) {
    gsap.fromTo(panel, { y: 12, scale: 0.985, opacity: 0 },
      {
        y: 0, scale: 1, opacity: 1, duration: 0.32, ease: 'power3.out',
        clearProps: 'transform,opacity',
      })
  }
}

export function drawerLeave(layer: Element | null, done: () => void): void {
  if (!layer || motionOff()) { done(); return }
  const mask = layer.querySelector('.drawer-mask')
  const panel = layer.querySelector('.sheet')
  const end = finish(done, 0.2)
  if (panel) gsap.to(panel, { y: 8, scale: 0.99, opacity: 0, duration: 0.18, ease: 'power2.in' })
  if (mask) gsap.to(mask, { opacity: 0, duration: 0.18, ease: 'power1.in', onComplete: end })
  else end()
}

/* ── 放：居中弹窗（比抽屉小，进出都短一档） ───────────────────── */
export function dialogEnter(layer: Element | null): void {
  if (!layer || motionOff()) return
  const mask = layer.querySelector('.cap-mask')
  const box = layer.querySelector('.cap-box')
  if (mask) gsap.fromTo(mask, { opacity: 0 }, { opacity: 1, duration: 0.18, ease: 'power2.out' })
  if (box) {
    gsap.fromTo(box, { y: 10, scale: 0.96, opacity: 0 },
      { y: 0, scale: 1, opacity: 1, duration: 0.3, ease: 'back.out(1.5)',
        clearProps: 'transform,opacity' })
  }
}

export function dialogLeave(layer: Element | null, done: () => void): void {
  if (!layer || motionOff()) { done(); return }
  const mask = layer.querySelector('.cap-mask')
  const box = layer.querySelector('.cap-box')
  const end = finish(done, 0.16)
  if (box) gsap.to(box, { y: 6, scale: 0.98, opacity: 0, duration: 0.14, ease: 'power2.in' })
  if (mask) gsap.to(mask, { opacity: 0, duration: 0.14, ease: 'power1.in', onComplete: end })
  else end()
}

/* ── 结：拖拽换位后的 FLIP ───────────────────────────────────── */
export function captureRects(root: HTMLElement | null): Map<string, DOMRect> {
  const map = new Map<string, DOMRect>()
  if (!root) return map
  root.querySelectorAll<HTMLElement>('.device-card').forEach((el) => {
    const did = el.dataset.did
    if (did) map.set(did, el.getBoundingClientRect())
  })
  return map
}

/** 按换位前后的矩形差反向补位移，再回到 0；不做布局动画也能看出因果。 */
export function flipCards(root: HTMLElement | null, before: Map<string, DOMRect>): void {
  if (!root || !before.size || motionOff()) return
  const moved: Array<{ el: HTMLElement; dx: number; dy: number }> = []
  root.querySelectorAll<HTMLElement>('.device-card').forEach((el) => {
    const did = el.dataset.did
    const old = did ? before.get(did) : null
    if (!old) return
    const now = el.getBoundingClientRect()
    const dx = old.left - now.left
    const dy = old.top - now.top
    if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return
    moved.push({ el, dx, dy })
  })
  if (!moved.length) return
  moved.forEach(({ el, dx, dy }) => {
    gsap.fromTo(el, { x: dx, y: dy },
      {
        x: 0, y: 0, duration: VOICE.settle.dur, ease: 'power3.out',
        clearProps: 'transform',
      })
  })
}

/* ── 放：场景砖按下 —— 水波从指尖散开，图标被「按下去又弹回来」 ── */
export function scenePress(el: Element | null, x: number, y: number): void {
  if (!el || motionOff()) return
  const host = el as HTMLElement
  const ico = host.querySelector('.st-ico')
  if (ico) {
    gsap.fromTo(ico, { scale: 0.9 },
      { scale: 1, duration: 0.34, ease: 'back.out(2.6)', clearProps: 'transform' })
  }
  const rip = document.createElement('span')
  /* 半径取点击点到最远角的距离：圆一定把整块砖盖满，不会露出一道弧形切边。
     铺开只给 0.2s，淡出给 0.4s —— 先「整块泛一下」再慢慢退，比长时间半块蓝干净。 */
  const w = host.offsetWidth
  const h = host.offsetHeight
  const r = Math.max(
    Math.hypot(x, y),
    Math.hypot(w - x, y),
    Math.hypot(x, h - y),
    Math.hypot(w - x, h - y),
  )
  rip.className = 'st-ripple'
  rip.setAttribute('aria-hidden', 'true')
  rip.style.left = (x - r) + 'px'
  rip.style.top = (y - r) + 'px'
  rip.style.width = r * 2 + 'px'
  rip.style.height = r * 2 + 'px'
  host.appendChild(rip)
  const tl = gsap.timeline({ onComplete: () => rip.remove() })
  tl.fromTo(rip, { scale: 0, opacity: 0.16 }, { scale: 1, opacity: 0.16, duration: 0.2, ease: 'power2.out' })
    .to(rip, { opacity: 0, duration: 0.4, ease: 'power1.out' })
}

/* ── 结：场景真的跑完了，砖块轻震一下作为「收到」 ─────────────── */
export function sceneSettle(el: Element | null): void {
  if (!el || motionOff()) return
  const host = el as HTMLElement
  gsap.fromTo(host, { scale: 1 },
    {
      scale: 1.015, duration: 0.13, yoyo: true, repeat: 1, ease: 'power2.out',
      /* 必须手动清掉内联变换：clearProps 会留下 translate(0,0) 与
         translate/scale/rotate 三条独立属性，内联的 transform 会压住
         CSS 的 hover 上浮，等于把这个按钮的悬停反馈弄没了。 */
      onComplete: () => {
        host.style.removeProperty('transform')
        host.style.removeProperty('translate')
        host.style.removeProperty('scale')
        host.style.removeProperty('rotate')
        if (!host.getAttribute('style')) host.removeAttribute('style')
      },
    })
}

/* ── 结：主题切换的一次性扫光，避免配色瞬时跳变 ───────────────── */
let veil: HTMLElement | null = null

export function themeSweep(color: string): void {
  if (motionOff()) return
  if (!veil) {
    veil = document.createElement('div')
    veil.className = 'theme-veil'
    veil.setAttribute('aria-hidden', 'true')
    document.body.appendChild(veil)
  }
  veil.style.background = color
  gsap.killTweensOf(veil)
  gsap.fromTo(veil, { opacity: 0.88 }, { opacity: 0, duration: 0.4, ease: 'power2.out' })
}

/* ── 停摆：场景执行中的小转圈（只在 busy 期间转，结束立刻停） ──── */
const spinning = new WeakMap<Element, Tween>()

export function spin(el: Element | null, on: boolean): void {
  if (!el) return
  const cur = spinning.get(el)
  if (!on) {
    if (cur) {
      cur.kill()
      spinning.delete(el)
      const node = el as HTMLElement
      for (const prop of ['transform', 'translate', 'rotate', 'scale', 'transform-origin']) {
        node.style.removeProperty(prop)
      }
      if (!node.getAttribute('style')) node.removeAttribute('style')
    }
    return
  }
  if (motionOff() || (cur && cur.isActive())) return
  spinning.set(el, gsap.to(el, {
    rotate: 360, duration: 0.9, repeat: -1, ease: 'none',
    transformOrigin: '50% 50%',
  }))
}

/* ── 停摆：控制中四周彩色描边环 ─────────────────────────────────
 * conic-gradient 的起点角 --ang 由 GSAP 连续补间（CSS 自定义属性注册在
 * tokens.css 的 @property --ang）。与 spin() 一样走 WeakMap，结束即清理；
 * motionOff 时停在静态起始角 —— 描边仍在（色彩提示不丢），只是不转。 */
const spinningEdge = new WeakMap<Element, Tween>()

export function spinEdge(el: Element | null, on: boolean): void {
  if (!el) return
  const cur = spinningEdge.get(el)
  if (!on) {
    if (cur) {
      cur.kill()
      spinningEdge.delete(el)
      ;(el as HTMLElement).style.removeProperty('--ang')
    }
    return
  }
  if (motionOff() || (cur && cur.isActive())) return
  const node = el as HTMLElement
  node.style.setProperty('--ang', '0deg')
  spinningEdge.set(el, gsap.to(node, {
    '--ang': '360deg', duration: 1.25, repeat: -1, ease: 'none',
  }))
}

/* ── 停摆：等结果时才呼吸，拿到结果立刻停 ─────────────────────── */
const breathing = new WeakMap<Element, Tween>()

export function breathe(el: Element | null, on: boolean): void {
  if (!el) return
  const cur = breathing.get(el)
  if (!on) {
    if (cur) {
      cur.kill()
      breathing.delete(el)
      gsap.set(el, { opacity: 1 })
    }
    return
  }
  if (motionOff() || (cur && cur.isActive())) return
  breathing.set(el, gsap.to(el, {
    opacity: 0.45, duration: VOICE.stall.dur, ease: VOICE.stall.ease,
    yoyo: true, repeat: -1,
  }))
}
