/* 自动化（智能场景）纯逻辑（Vue 版）。
 *
 * 与 static/app.js 的 renderAutomations / fillCreateTemplates /
 * syncAutomationDrawer / autoDeleteSection / applyAutomation 同源：
 * 字段、按家庭筛选、模板筛选、四个详情区块、确认文案、名称复核一字不改。
 * 写入仍沿用后端规则：confirm=true 才发请求，删除还需名称完全一致。
 */
import type {
  AutomationDetail, AutomationItem, AutomationPatch, AutoEntry,
} from './types'

export const AUTO_NOTE =
  '支持改名、启停、新建与删除；写入均需二次确认，删除需手动输入完整名称复核。'
export const CREATE_TITLE = '新建自动化 · 复制现有自动化的触发、条件与动作'
export const CREATE_DANGER = '创建会同步到米家 App 与家庭共享成员；删除不可撤销。'
export const NO_TEMPLATE = '没有可用模板（需含触发与动作）'
export const PREVIEW_HINT = '请先填写名称并选择模板，再预览将要发送的请求。'
export const EDIT_HINT =
  '改完名称或点过启停后，可点「预览请求内容」核对即将发给米家的完整请求；' +
  '这里只本地生成，不会写入。'
export const EDIT_READONLY = '写入接口尚未开放，当前只能查看。'
export const PREVIEW_NEED_CHANGE =
  '当前没有改动，所以没有要发送的内容。先改名称或点「启用/停用」，再看这里。'
export const PREVIEW_NOTE = '这一段只是预览：点「创建 / 保存名称」之类才会真的发给米家。'
export const DELETE_SECTION_TITLE = '危险操作 · 删除（不可撤销）'
export const DELETE_SECTION_TEXT =
  '删除会同步到米家 App 与家庭共享成员，无法恢复。请先完整输入该自动化名称作为复核。'
export const RAW_SUMMARY = '查看原始数据（JSON）'
export const EDIT_TITLE = '编辑 · 改名与启停（会真实同步到米家 App）'

export function countText(count: number, enabled: number): string {
  return count + ' 条 · 启用 ' + enabled
}

/** 标题副标签：家庭名 + 条数。自动化是家庭级的，标题里点明是哪一家。 */
export function headText(home: string, count: number, enabled: number): string {
  const base = countText(count, enabled)
  return home ? home + ' · ' + base : base
}

/** 空态：当前家庭一条自动化都没有（别家的不在这里显示）。 */
export function emptyText(home: string): string {
  return (home || '当前家庭') + ' 还没有自动化'
}
export const EMPTY_HINT =
  '自动化按家庭独立：每条只对所在家庭的设备生效。切到顶部别的家庭，能看到那边的自动化。'

export function autoMeta(a: AutomationItem): string {
  const c = a.counts || { trigger: 0, condition: 0, action: 0 }
  return '触发 ' + c.trigger + ' · 条件 ' + c.condition + ' · 动作 ' + c.action
}

/** 模板下拉只列含有效触发与动作的自动化（空触发会被云端拒绝）。 */
export function usableTemplates(items: AutomationItem[]): AutomationItem[] {
  return items.filter((a) => a.counts.trigger > 0 && a.counts.action > 0)
}

/** 用 scene_id 签名判断是否需要重建模板下拉，避免刷新列表时清空已填表单。 */
export function templateSignature(items: AutomationItem[]): string {
  return usableTemplates(items).map((a) => a.scene_id).join('|')
}

export function templateOptionText(a: AutomationItem): string {
  return (a.enable ? '启用 · ' : '停用 · ') + a.name
}

export interface CreateForm {
  template_scene_id: string
  name: string
  enable: boolean
}

export function createFormPayload(name: string, templateId: string, enable: boolean): CreateForm {
  return {
    template_scene_id: templateId || '',
    name: (name || '').trim(),
    enable: Boolean(enable),
  }
}

export function createConfirmText(p: CreateForm, tplName: string): string {
  return '将复制「' + (tplName || p.template_scene_id) +
    '」的触发、条件与动作，新建一条自动化：\n\n' +
    '名称：' + p.name + '\n状态：' + (p.enable ? '立即启用' : '停用（推荐）') +
    '\n\n改动会同步到米家 App 与家庭共享成员，确认创建？'
}

export function applyConfirmText(patch: AutomationPatch): string {
  if (patch.name !== undefined) {
    return '把自动化名称改为「' + patch.name + '」并同步到米家云端？'
  }
  const word = patch.enable ? '启用' : '停用'
  return word + '这条自动化？改动会同步到米家 App 和家人设备。'
}

export function deleteConfirmText(name: string): string {
  return '将永久删除自动化「' + name + '」？\n\n' +
    '此操作不可撤销，米家 App 与家庭共享成员处都会消失。'
}

export function deleteNameMatch(input: string, item: AutomationItem): boolean {
  return input === item.name
}

export const NAME_EMPTY = '名称不能为空'
export const NAME_SAME = '名称没有变化'
export const NAME_MISMATCH = '名称复核不一致，请完整输入自动化名称'
export const PLEASE_NAME = '请先填写名称'
export const PLEASE_TEMPLATE = '请选择模板'

/** 详情弹框的四个区块，顺序与旧版一致，空数组不渲染。 */
export function detailBlocks(item: AutomationDetail): Array<[string, AutoEntry[]]> {
  return [
    ['触发', item.triggers || []],
    ['条件', item.conditions || []],
    ['执行', item.actions || []],
    ['否则', item.else_actions || []],
  ]
}

export function entryDevice(e: AutoEntry): string { return e.device || '—' }
export function entryName(e: AutoEntry): string { return e.name || e.key || '—' }
export function entryValue(e: AutoEntry): string {
  if (e.value === undefined || e.value === null || e.value === '') return ''
  return '值 ' + JSON.stringify(e.value)
}

export function updateTimeText(item: AutomationDetail): string {
  if (!item.update_time) return '—'
  const t = new Date(Number(item.update_time) * 1000)
  if (isNaN(t.getTime())) return '—'
  return t.toLocaleString('zh-CN')
}

export function detailHead(item: AutomationDetail): string {
  return (item.home_name || '') + ' · ' + (item.enable ? '已启用' : '已停用') +
    ' · 更新于 ' + updateTimeText(item)
}

export function createOutput(res: {
  ok: boolean; error?: string; result?: unknown; created_id?: string | number
}): string {
  if (!res.ok) return '创建失败：' + (res.error || '未知错误')
  return '创建成功，云端返回：' + JSON.stringify(res.result) +
    '\n新 scene_id：' + (res.created_id || '（云端未返回）')
}

export function applyOutput(res: {
  ok: boolean; error?: string; result?: unknown; preview?: { changes?: unknown }
}): string {
  if (!res.ok) return '写入失败：' + (res.error || '未知错误')
  return '写入成功，云端返回：' + JSON.stringify(res.result) +
    '\n改动内容：' + JSON.stringify(res.preview?.changes, null, 2)
}

export function deleteOutput(res: { ok: boolean; error?: string }): string {
  return res.ok ? '' : '删除失败：' + (res.error || '未知错误')
}

/** 预览用的字段中文名：后端返回的是 name / enable / scene_trigger 这类机器名。 */
const OP_LABEL: Record<string, string> = {
  create: '新建', edit: '修改', delete: '删除',
}
const FIELD_LABEL: Record<string, string> = {
  name: '名称', enable: '状态', deleted: '删除对象',
  scene_trigger: '触发', scene_condition: '条件', scene_action: '动作',
  scene_else_action: '否则动作', scene_time_window: '生效时段',
}

function previewValue(v: unknown): string {
  if (v === null || v === undefined) return '（空）'
  if (typeof v === 'boolean') return v ? '启用' : '停用'
  if (typeof v === 'string') return v === '' ? '（空）' : v
  if (Array.isArray(v)) return v.length + ' 项'
  if (typeof v === 'object') return '结构体'
  return String(v)
}

/** 把 preview 对象翻成「发给哪个端点 + 改了哪几项 + 完整请求体」三段人话。 */
export function previewText(p: unknown): string {
  const o = (p || {}) as Record<string, unknown>
  const op = OP_LABEL[String(o.operation || '')] || '写入'
  const uri = String(o.uri || '')
  const changes = Array.isArray(o.changes)
    ? (o.changes as Array<Record<string, unknown>>)
    : []
  const lines = ['将要发送：' + op + (uri ? ' · 端点 ' + uri : '')]
  if (changes.length) {
    lines.push('改动 ' + changes.length + ' 项：')
    for (const c of changes) {
      const k = String(c.field || '')
      lines.push('  ' + (FIELD_LABEL[k] || k) + '：' + previewValue(c.from) +
        ' → ' + previewValue(c.to))
    }
  } else {
    lines.push('改动 0 项（与云端现有内容一致）')
  }
  lines.push('', PREVIEW_NOTE, '', '完整请求体（JSON）：', JSON.stringify(p, null, 2))
  return lines.join('\n')
}

export function previewOutput(res: { ok: boolean; error?: string; preview?: unknown }): string {
  return res.ok ? previewText(res.preview) : (res.error || '预览生成失败')
}
