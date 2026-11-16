/* 在线升级数据层（Vue 版）。
 *
 * 对应后端 routes/update.py 的五个接口：
 *   GET  /api/update/info      关于信息
 *   POST /api/update/check     检测新版本
 *   POST /api/update/apply     下载并升级
 *   POST /api/update/rollback  回滚到升级前
 *   POST /api/update/restart   手动重启
 *
 * 与设备 store 一样，所有请求都带回执结构，不做乐观更新——升级这种事
 * 只认后端确认，避免界面先宣布成功而实际失败。
 */
import { ref } from 'vue'
import { defineStore } from 'pinia'

export type UpdateAsset = {
  name: string
  size: number
  url: string
  digest: string
}
export type Release = {
  tag: string
  version: string
  name: string
  body: string
  url: string
  published_at: string
  asset: UpdateAsset | null
}
export type UpdateInfo = {
  ok: boolean
  name: string
  version: string
  homepage: string
  configured: boolean
  auto_restart: boolean
  last: Record<string, unknown>
  backups: string[]
}
export type CheckResult = {
  ok: boolean
  error: string
  configured: boolean
  current: string
  homepage: string
  repo: string
  has_update?: boolean
  latest?: Release
}
export type ApplyResult = {
  ok: boolean
  error?: string
  noop?: boolean
  from?: string
  to?: string
  tag?: string
  backup?: string
  changed?: number
  restart_required?: boolean
  auto_restart?: boolean
}

type Ack = { ok: boolean; error?: string; message?: string }

async function apiGet<T>(path: string): Promise<T> {
  const r = await fetch(path)
  return (await r.json()) as T
}
async function apiPost<T>(path: string): Promise<T> {
  const r = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  })
  return (await r.json()) as T
}

export const useUpdateStore = defineStore('update', () => {
  const info = ref<UpdateInfo | null>(null)
  const checkResult = ref<CheckResult | null>(null)
  const busy = ref<'check' | 'apply' | 'rollback' | 'restart' | ''>('')
  const note = ref('')          // 一行状态提示，直接显示在弹窗里
  const noteTone = ref<'ok' | 'warn' | ''>('')

  function setNote(text: string, tone: 'ok' | 'warn' | '' = ''): void {
    note.value = text
    noteTone.value = tone
  }

  async function bootstrap(): Promise<void> {
    try {
      info.value = await apiGet<UpdateInfo>('/api/update/info')
    } catch {
      // 关于窗口是附加功能，取不到信息也不影响主界面
    }
  }

  async function check(): Promise<void> {
    if (busy.value) return
    busy.value = 'check'
    setNote('正在连接 GitHub 检测新版本…')
    checkResult.value = null
    try {
      const res = await apiPost<CheckResult>('/api/update/check')
      checkResult.value = res
      if (!res.ok) {
        setNote(res.error || '检测失败', 'warn')
      } else if (res.has_update && res.latest) {
        setNote(`发现新版本 ${res.latest.tag}`, 'ok')
      } else {
        setNote('当前已是最新版本', 'ok')
      }
    } catch {
      setNote('检测失败：无法连接后端', 'warn')
    } finally {
      busy.value = ''
    }
  }

  async function apply(): Promise<ApplyResult | null> {
    if (busy.value) return null
    busy.value = 'apply'
    setNote('正在下载升级包并安装，请勿关闭页面…')
    try {
      const res = await apiPost<ApplyResult>('/api/update/apply')
      if (!res.ok) {
        setNote(res.error || '升级失败', 'warn')
      } else if (res.restart_required && res.auto_restart) {
        setNote(`已升级到 ${res.tag}，服务正在重启，页面即将刷新…`, 'ok')
      } else if (res.restart_required) {
        setNote(`已升级到 ${res.tag}，请手动重启服务后刷新页面`, 'ok')
      } else {
        setNote(res.error || '当前已是最新版本', 'ok')
      }
      void bootstrap()
      return res
    } catch {
      setNote('升级失败：无法连接后端', 'warn')
      return null
    } finally {
      busy.value = ''
    }
  }

  async function rollback(): Promise<void> {
    if (busy.value) return
    busy.value = 'rollback'
    setNote('正在回滚到升级前的版本…')
    try {
      const res = await apiPost<Ack & { restart_required?: boolean }>('/api/update/rollback')
      if (res.ok) {
        setNote('已回滚，服务正在重启…', 'ok')
      } else {
        setNote(res.error || '回滚失败', 'warn')
      }
      void bootstrap()
    } catch {
      setNote('回滚失败：无法连接后端', 'warn')
    } finally {
      busy.value = ''
    }
  }

  async function restart(): Promise<void> {
    if (busy.value) return
    busy.value = 'restart'
    setNote('正在重启服务…')
    try {
      const res = await apiPost<Ack>('/api/update/restart')
      setNote(res.message || '服务即将重启', 'ok')
    } catch {
      setNote('重启失败：无法连接后端', 'warn')
    } finally {
      busy.value = ''
    }
  }

  function reset(): void {
    checkResult.value = null
    setNote('')
  }

  return { info, checkResult, busy, note, noteTone, bootstrap, check, apply,
           rollback, restart, reset }
})
