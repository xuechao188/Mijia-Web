/* 设备详情增强的数据层（Vue 版，步骤⑤）。
 *
 * 只覆盖弹框里的摄像头专项（/api/camera/*）。④ 已验收的 devices.ts
 * 一行不改，避免回归。定时规则已整体下线：自动化面板能覆盖同一诉求，
 * 两套入口并存只会让人不知道去改哪一个。
 *
 * 保留旧界面两个踩过坑才定下的行为：
 *   1) 取流结果按 did 缓存：旧版抽屉每 3 秒整块重建，结果存在
 *      state.cameraStream[did] 才不会被冲掉；Vue 虽不重建 DOM，但抽屉
 *      开关/切设备时同样要保留，故仍按 did 存。
 *   2) 拿不到可播地址就如实说明 + 原始返回，绝不伪造播放器。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'
import {
  STREAM_BUSY, STREAM_NETERR, STREAM_STOPPED,
  type CameraAction, type CameraCapability, type CamTip, type CapResponse, type StreamResult,
} from '../devices/camera'
import { useDevicesStore } from './devices'

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path)
  return (await r.json()) as T
}
async function apiPost<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  return (await r.json()) as T
}

export const useDetailStore = defineStore('detail', () => {
  const devices = useDevicesStore()

  const streams = ref<Record<string, StreamResult>>({})
  const streamNotes = ref<Record<string, string>>({})
  const streamBusy = ref<Record<string, boolean>>({})
  /* 取流能力判定：这台设备到底能不能在 PC 上出画面。按 did 存，切设备不丢。 */
  const caps = ref<Record<string, CameraCapability>>({})
  const capBusy = ref<Record<string, boolean>>({})
  const capError = ref<Record<string, string>>({})
  /* 播不出来时的弹窗内容。null 表示没有弹窗；一次只弹一个（抽屉只看一台设备）。 */
  const tip = ref<CamTip | null>(null)

  function closeTip(): void {
    tip.value = null
  }

  /** 问后端要判定（后端有 10 分钟缓存，force 时重测）。 */
  async function checkCapability(did: string, force = false): Promise<void> {
    capBusy.value = { ...capBusy.value, [did]: true }
    try {
      const q = `/api/camera/capability?did=${encodeURIComponent(did)}` + (force ? '&force=1' : '')
      const r = await apiGet<CapResponse>(q)
      if (r.ok && r.capability) {
        caps.value = { ...caps.value, [did]: r.capability }
        const nextErr = { ...capError.value }
        delete nextErr[did]
        capError.value = nextErr
      } else {
        capError.value = { ...capError.value, [did]: r.error || '检测失败' }
      }
    } catch {
      capError.value = { ...capError.value, [did]: '网络异常' }
    } finally {
      capBusy.value = { ...capBusy.value, [did]: false }
    }
  }

  /* ---------------- 摄像头：取流 ----------------
   * 判定并进这一步：点「获取实时画面」时后端先看这台能不能播，播不了就
   * 直接回 capability，不再去撞一次必然失败的 start-p2p-stream。前端拿到
   * 结论就弹窗，平时抽屉里不留任何常驻状态。
   */
  async function getStream(did: string): Promise<void> {
    streamBusy.value = { ...streamBusy.value, [did]: true }
    streamNotes.value = { ...streamNotes.value, [did]: STREAM_BUSY }
    closeTip()
    try {
      const r = await apiPost<StreamResult>('/api/camera/stream', { did })
      if (r.capability) caps.value = { ...caps.value, [did]: r.capability }
      if (r.ok !== false && r.playable && r.url) {
        streams.value = { ...streams.value, [did]: r }
        streamNotes.value = { ...streamNotes.value, [did]: '' }
        return
      }
      // 播不了：清掉旧流，原因交给弹窗，不在面板里堆文字
      const next = { ...streams.value }
      delete next[did]
      streams.value = next
      streamNotes.value = { ...streamNotes.value, [did]: '' }
      tip.value = {
        did,
        cap: r.capability || null,
        note: r.ok === false ? (r.hint || r.error || '') : (r.note || ''),
        rawText: (r.raw === undefined || r.raw === null) ? '' : JSON.stringify(r.raw, null, 2),
      }
    } catch {
      streamNotes.value = { ...streamNotes.value, [did]: '' }
      tip.value = { did, cap: null, note: STREAM_NETERR, rawText: '' }
    } finally {
      streamBusy.value = { ...streamBusy.value, [did]: false }
    }
  }

  /** 弹窗里的「重新检测 / 我已连到同一网络」：强制重测，可播就立刻接着取流。 */
  async function retryTip(): Promise<void> {
    const cur = tip.value
    if (!cur) return
    await checkCapability(cur.did, true)
    const cap = caps.value[cur.did] || null
    if (cap && (cap.mode === 'wan' || cap.mode === 'lan' || cap.mode === 'unknown')) {
      await getStream(cur.did)
      return
    }
    // 结论没变（或探测仍失败）：就地更新弹窗，不闪一下再弹第二个
    tip.value = { ...cur, cap, note: cap ? '' : (capError.value[cur.did] || cur.note) }
  }

  async function stopStream(did: string): Promise<void> {
    try {
      await apiPost<{ ok: boolean; error?: string; hint?: string }>('/api/camera/stop', { did })
      const next = { ...streams.value }
      delete next[did]
      streams.value = next
      streamNotes.value = { ...streamNotes.value, [did]: STREAM_STOPPED }
    } catch {
      devices.toast('停止取流失败')
    }
  }

  /* ---------------- 摄像头：动作 ---------------- */
  async function runAction(did: string, a: CameraAction): Promise<void> {
    try {
      const r = await apiPost<{ ok: boolean; error?: string; hint?: string }>(
        '/api/camera/action', { did, siid: a.siid, aiid: a.aiid },
      )
      if (!r.ok) devices.toast(r.hint || r.error || '动作执行失败')
      else devices.toast('已发送：' + a.name)
    } catch {
      devices.toast('网络异常')
    }
  }

  function clearStreamNote(did: string): void {
    if (!streamNotes.value[did]) return
    streamNotes.value = { ...streamNotes.value, [did]: '' }
  }

  return {
    streams, streamNotes, streamBusy,
    caps, capBusy, capError, checkCapability,
    tip, closeTip, retryTip,
    getStream, stopStream, runAction, clearStreamNote,
  }
})
