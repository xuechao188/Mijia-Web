/* 摄像头动作分类与取流文案（纯函数，无 DOM 依赖）。
 *
 * 与 static/camera_panel.js 一一对应：白名单/黑名单/方向盘顺序/符号全部沿用，
 * 保证新版抽屉不会比旧界面多暴露任何一个破坏性动作。
 *
 * 事实约束：小米摄像头走专有 P2P，start-p2p-stream 返回的是取流令牌而非
 * 浏览器可播地址，PC 端没有 ffmpeg 常驻中继就出不了画面。因此只"尽力取流"，
 * 拿不到就如实说明并展示原始返回，绝不伪造播放器。
 */
export interface CameraAction {
  siid: number
  aiid: number
  name: string
  svc?: string
}

export interface CameraClassify {
  ptz: CameraAction[]
  others: CameraAction[]
  denied: CameraAction[]
}

export const PTZ_SYMBOLS: Record<string, string> = {
  'pan-left': '←', 'pan-right': '→', 'tilt-up': '↑', 'tilt-down': '↓',
  'zoom-in': '＋', 'zoom-out': '－', 'rotate': '⟳',
  'rotate-left': '↺', 'rotate-right': '↻',
  'go-to-preset': '预设', 'ptz': '云台', 'ptz-control': '云台',
}

/** 仅白名单内的非破坏性动作才给通用按钮。 */
export const SAFE_ACTION = /^(pan-|tilt-|zoom-|rotate|go-to-preset|ptz|snapshot|calibration|flip|mirror|led|indicator|alarm|siren|notify|mute|volume|talk|push|enable|disable|move)/i
/** 破坏性 / 危险动作无论是否认得都不暴露按钮（格式化存储卡等）。 */
export const DENY_ACTION = /^(format|delete|reset|factory|restore|reboot|power-off|pop-up|eject|clear|remove|add)/i

/** 方向盘五格：上、左、中、右、下；中间是 ptz 占位。 */
export const DIRECTIONS = ['tilt-up', 'pan-left', 'ptz', 'pan-right', 'tilt-down'] as const

export const NO_PTZ_NOTE = '此摄像头型号未在 MIoT 标准协议中暴露云台/可控动作' +
  '（旧款创米摄像头通过私有协议控制，PC 端无法直接驱动）。'
export const PLACEHOLDER_IDLE = '实时画面需从设备取流'
export const PLACEHOLDER_FAILED = '该设备无法在 PC 浏览器直接出画面'
export const STREAM_BUSY = '正在向设备请求取流…'
export const STREAM_OK = '已拿到可播放地址（部分地址浏览器可能不支持）。'
export const STREAM_EMPTY = '未能取到可播放画面。'
export const STREAM_STOPPED = '已发送停止取流。'
export const STREAM_NETERR = '网络异常，取流未成功'
export const RAW_SUMMARY = '查看设备返回的原始数据'

export function classify(actions: CameraAction[] | null | undefined): CameraClassify {
  const ptz: CameraAction[] = []
  const others: CameraAction[] = []
  const denied: CameraAction[] = []
  for (const a of actions || []) {
    if ((a.svc || '').indexOf('p2p-stream') >= 0) continue // 取流单独处理
    if (PTZ_SYMBOLS[a.name]) { ptz.push(a); continue }
    if (DENY_ACTION.test(a.name)) { denied.push(a); continue }
    if (SAFE_ACTION.test(a.name)) { others.push(a); continue }
    denied.push(a) // 其余未白名单动作保守不暴露
  }
  return { ptz, others, denied }
}

/** 方向盘每一格对应的动作；没命中就是空格子。 */
export function directionAction(
  name: string, actions: CameraAction[],
): CameraAction | null {
  for (const a of actions) if (a.name === name) return a
  return null
}

export interface StreamResult {
  ok?: boolean
  playable?: boolean
  url?: string | null
  note?: string | null
  error?: string
  hint?: string
  raw?: unknown
  /** 后端取流前顺带给出的判定，播不了时直接用它组织弹窗 */
  capability?: CameraCapability
}

export interface StreamView {
  mode: 'playable' | 'fallback'
  url: string | null
  note: string
  rawText: string | null
}

/** applyStream 的纯逻辑部分：Vue 组件只负责把结果贴到 DOM。 */
export function streamView(r: StreamResult): StreamView {
  if (r.playable && r.url) {
    return { mode: 'playable', url: r.url, note: STREAM_OK, rawText: null }
  }
  const rawText = (r.raw === undefined || r.raw === null)
    ? null : JSON.stringify(r.raw, null, 2)
  return {
    mode: 'fallback', url: null,
    note: r.note || STREAM_EMPTY, rawText,
  }
}

/** 取流请求失败时的提示，与旧版 alert 文案一致。 */
export function streamFailure(r: StreamResult): string {
  return '取流失败：' + (r.hint || r.error || '')
}

/* ---------------------------------------------------------------- 取流能力
 *
 * 米家摄像头横跨三代 P2P 固件，PC 端只有 CS2/MTP 有实现（官方 PC 版原生库
 * 把 TUTK 通道裁掉了，实机日志 `Can't support TUTK vendor.`）。老 TUTK 机型
 * 只能在同一局域网里播，跨网络无论如何都出不了画面。所以面板打开时先问后端
 * 「这台能不能播」，能播才给按钮，不能播就把条件讲清楚。
 */
export type CapMode = 'wan' | 'lan' | 'lan_only' | 'unsupported' | 'offline' | 'unknown'

export interface CameraCapability {
  mode: CapMode
  remote_playable: boolean
  title: string
  reason: string
  advice: string
  same_lan?: boolean | null
  lan_reachable?: boolean | null
  vendor?: string | null
  checked_at?: number
  cached?: boolean
  evidence?: Record<string, unknown>
}

export interface CapResponse {
  ok?: boolean
  capability?: CameraCapability
  error?: string
}

export interface CapView {
  /** 徽标语气：ok 绿 / warn 黄 / muted 灰 */
  tone: 'ok' | 'warn' | 'muted'
  title: string
  detail: string
  /** 视频区的占位文案 */
  placeholder: string
  /** 是否值得点「获取实时画面」 */
  canTry: boolean
}

export const CAP_CHECKING = '正在检测取流能力…'
export const CAP_FAILED = '取流能力检测失败'

const CAP_PLACEHOLDER: Record<CapMode, string> = {
  wan: PLACEHOLDER_IDLE,
  lan: PLACEHOLDER_IDLE,
  lan_only: '需在同一局域网内才能播放',
  unsupported: '该设备不支持在 PC 端取流',
  offline: '设备离线，无法取流',
  unknown: PLACEHOLDER_IDLE,
}

const CAP_TONE: Record<CapMode, CapView['tone']> = {
  wan: 'ok',
  lan: 'warn',
  lan_only: 'warn',
  unsupported: 'muted',
  offline: 'muted',
  unknown: 'muted',
}

/** 把后端判定翻成界面要的三样东西：徽标、说明、占位文案。 */
export function capView(cap: CameraCapability | null | undefined): CapView | null {
  if (!cap || !cap.mode) return null
  const mode = cap.mode
  return {
    tone: CAP_TONE[mode] || 'muted',
    title: cap.title || CAP_FAILED,
    // 中文句子直接相连，不加空格（两个半句各自以句号收尾）
    detail: [cap.reason, cap.advice].filter(Boolean).join(''),
    placeholder: CAP_PLACEHOLDER[mode] || PLACEHOLDER_IDLE,
    // lan 也可以点：同网段时局域网直连是真能出画面的
    canTry: mode === 'wan' || mode === 'lan' || mode === 'unknown',
  }
}

/** 厂商标识给界面看的中文名。 */
export function vendorLabel(v?: string | null): string {
  const map: Record<string, string> = {
    tutk: 'TUTK 固件', cs2: 'CS2 固件', mtp: 'MTP 固件', agora: 'Agora 固件',
  }
  return v ? (map[v] || v.toUpperCase()) : ''
}

/* ---------------------------------------------------------------- 失败弹窗
 *
 * 判定不再常驻面板：抽屉一打开就摆一条「仅支持局域网」的横幅，多数时候
 * 用户并不会去看实时画面，那条横幅只是占地方。改成点了「获取实时画面」
 * 播不出来时才弹一次，把原因、条件、原始返回放在弹窗里，看完即关。
 */
export interface CamTip {
  did: string
  cap: CameraCapability | null
  /** 设备级结论之外的兜底说明（检测失败 / 云端报错 / 网络异常） */
  note: string
  /** 后端原始返回，弹窗里折叠展示 */
  rawText: string
}

export interface CapDialogView {
  tone: CapView['tone']
  title: string
  reason: string
  advice: string
  vendor: string
  note: string
  /** 主行动按钮：老固件换网络后重测，语义比「重试」明确 */
  action: string
}

export const CAP_TIP_FALLBACK = '暂时无法播放实时画面'

export function capDialog(
  cap: CameraCapability | null | undefined, note = '',
): CapDialogView {
  const v = capView(cap)
  if (!v) {
    // 没拿到判定（探测失败/网络异常）：不猜原因，只把后端的话原样给出去
    return {
      tone: 'muted', title: CAP_TIP_FALLBACK, reason: '', advice: '',
      vendor: '', note: note || STREAM_EMPTY, action: '重新检测',
    }
  }
  return {
    tone: v.tone,
    title: v.title,
    reason: cap?.reason || '',
    advice: cap?.advice || '',
    vendor: vendorLabel(cap?.vendor),
    note: '',
    // 只支持局域网的机型，用户能做的事是「换个网络」，不是「重试」
    action: cap?.mode === 'lan_only' ? '我已连到同一网络' : '重新检测',
  }
}
