/* 读数滚动指令：数字变了才滚，格式变了就直接换。
 *
 * 用法：<span v-count>{{ r.text }}</span>
 * 目标文本始终来自模板（如 "24.5℃"），指令只负责中间过程；
 * 前后格式除了数字部分必须一致，否则（开→关、24℃→--）不滚，
 * 免得把状态切换演成数字乱跳。
 */
import gsap from 'gsap'
import type { ObjectDirective } from 'vue'
import { motionOff } from './index'
import { VOICE } from './voice'

const NUM = /-?\d+(?:\.\d+)?/

export const vCount: ObjectDirective<HTMLElement> = {
  mounted(el) {
    el.dataset.countText = el.textContent || ''
  },
  updated(el) {
    const next = el.textContent || ''
    const prev = el.dataset.countText || ''
    el.dataset.countText = next
    if (prev === next || motionOff()) return
    const a = prev.match(NUM)
    const b = next.match(NUM)
    if (!a || !b) return
    if (prev.replace(a[0], '#') !== next.replace(b[0], '#')) return
    const from = Number(a[0])
    const to = Number(b[0])
    if (!isFinite(from) || !isFinite(to) || from === to) return
    const digits = (b[0].split('.')[1] || '').length
    const box = { v: from }
    gsap.to(box, {
      v: to,
      duration: VOICE.settle.dur * 2.2,
      ease: VOICE.settle.ease,
      overwrite: true,
      onUpdate() {
        el.textContent = next.replace(b[0], box.v.toFixed(digits))
      },
      onComplete() {
        el.textContent = next
      },
    })
  },
}
