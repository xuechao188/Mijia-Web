/* 第 2 层之外的一层：动效语态表。
 *
 * 全站只允许四种语态，组件里不许写裸 duration / ease，避免每个地方
 * 各auto一套节奏。四种语态对应界面上的四类时刻：
 *
 *   放 release —— 元素第一次落到页面上（卡片入场、抽屉拉出）
 *   导 guide   —— 从一处到另一处（切换主标签页）
 *   结 settle  —— 一次操作有了结果（数值落定、拖拽归位）
 *   停摆 stall —— 没有结果，只能等（同步中、后端未连通）
 *
 * 时长都压在 0.2–0.46s，停摆的呼吸是 1.9s 的极慢循环。
 */
export const VOICE = {
  release: { dur: 0.38, ease: 'power3.out', rise: 12, scale: 0.985, stagger: 0.018 },
  guide: { dur: 0.18, ease: 'power2.out', rise: 6 },
  settle: { dur: 0.24, ease: 'power2.out' },
  stall: { dur: 1.9, ease: 'sine.inOut' },
} as const

export type VoiceName = keyof typeof VOICE
