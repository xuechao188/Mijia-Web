/* 手动场景纯逻辑（Vue 版）。
 * 与 static/app.js 的 loadScenes() 同源：/api/scenes 拉列表，
 * /api/scenes/run 带 scene_id + home_id + owner_uid + name 执行，
 * 结果只 toast，不臆造状态；执行后由调用方刷新事件流。
 */
import type { ApiResult, SceneItem } from './types'

export const SCENE_EMPTY = '暂无手动场景'
export const SCENE_FAILED = '场景执行失败'

export function sceneLabel(s: SceneItem): string {
  return s.name || '场景' + s.scene_id
}

/** 米家里常有一串同名场景（同一条「灯全关」复制成好几条）。
 * 名称本身不动，只给第 2 条起标一个序号，避免一排一模一样的按钮。 */
export function dupeIndex(list: SceneItem[]): Record<string, number> {
  const seen: Record<string, number> = {}
  const out: Record<string, number> = {}
  for (const s of list || []) {
    const key = sceneLabel(s).trim()
    const n = (seen[key] || 0) + 1
    seen[key] = n
    if (n > 1) out[s.scene_id] = n
  }
  return out
}

export function runPayload(s: SceneItem): {
  scene_id: string; home_id: string; owner_uid?: number; name: string
} {
  return {
    scene_id: s.scene_id,
    home_id: s.home_id,
    owner_uid: s.owner_uid,
    name: s.name,
  }
}

export function runToast(res: ApiResult, s: SceneItem): string {
  return res.ok ? '场景已执行：' + s.name : (res.error || SCENE_FAILED)
}
