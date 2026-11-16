<script setup lang="ts">
/* 自动化面板：与旧界面 #automation-panel 同源，但去掉了「折叠」这一层。
 *
 * 两条产品约定：
 *  一、不折叠。自动化是独立 tab，进来就是要看全部条目，再点一次展开纯属多一步；
 *      「新建」表单仍是就地展开/收起（那是表单，不是列表）。
 *  二、按家庭隔离。自动化属于家庭，顶部选了哪个家庭就只列哪个家庭的那批；
 *      新建时的模板也只在当前家庭里选，避免把这条复制到别人家里去。
 *
 * 写入统一走 panels store 的 confirm=true，二次确认在组件层。
 */
import { computed, ref, watch } from 'vue'
import {
  AUTO_NOTE, CREATE_DANGER, CREATE_TITLE, EMPTY_HINT, NO_TEMPLATE, PREVIEW_HINT,
  PLEASE_NAME, PLEASE_TEMPLATE, autoMeta, createConfirmText,
  createFormPayload, createOutput, emptyText, headText, previewOutput,
  templateOptionText, usableTemplates,
} from '../panels/automations'
import { usePanelsStore } from '../stores/panels'

const store = usePanelsStore()
const newName = ref('')
const templateId = ref('')
const newEnable = ref(false)
const createOut = ref('')

/* 模板只在当前家庭里挑：新建沿用模板的 home_id，跨家庭选模板等于建到别人家。 */
const usable = computed(() => usableTemplates(store.scopedAutomations))
const hasTemplate = computed(() => usable.value.length > 0)
const showCreate = computed(() =>
  store.autoCreateOpen && store.autoCreateSupported)
const items = computed(() => store.scopedAutomations)
const headSub = computed(() => headText(store.autoHomeName, store.autoCount, store.autoEnabled))

/* 旧版 <select> 默认选中第一项；刷新列表或切家庭后只要原模板还在就保留选择。 */
watch(usable, (list) => {
  if (!list.length) { templateId.value = ''; return }
  if (!list.some((a) => a.scene_id === templateId.value)) {
    templateId.value = list[0].scene_id
  }
}, { immediate: true })

function onTemplateChange(e: Event): void {
  templateId.value = (e.target as HTMLSelectElement).value
}
function form() {
  return createFormPayload(newName.value, templateId.value, newEnable.value)
}

async function previewCreate(): Promise<void> {
  const p = form()
  if (!p.name || !p.template_scene_id) { createOut.value = PREVIEW_HINT; return }
  createOut.value = '正在生成本地预览…'
  const r = await store.previewCreate(p)
  createOut.value = previewOutput(r as { ok: boolean; error?: string; preview?: unknown })
}

async function submitCreate(): Promise<void> {
  const p = form()
  if (!p.name) { store.toast(PLEASE_NAME); return }
  if (!p.template_scene_id) { store.toast(PLEASE_TEMPLATE); return }
  const tpl = items.value.find((a) => a.scene_id === p.template_scene_id)
  if (!window.confirm(createConfirmText(p, tpl ? tpl.name : ''))) return
  createOut.value = '正在写入米家云端…'
  const r = await store.createAutomation(p)
  createOut.value = createOutput(r as {
    ok: boolean; error?: string; result?: unknown; created_id?: string | number
  })
  if (!r.ok) return
  newName.value = ''
  newEnable.value = false
  const sid = r.created_id ? String(r.created_id) : ''
  if (sid && store.automations.some((a) => a.scene_id === sid)) {
    void store.openAutoDetail(sid)
  }
}
</script>

<template>
  <section class="automation-panel m-surface">
    <div class="auto-head">
      <div class="auto-title">
        自动化 <span class="auto-count mono">{{ headSub }}</span>
      </div>
      <div class="btn-wrap auto-actions">
        <button v-if="store.autoCreateSupported" type="button" class="btn sm"
                @click="store.toggleAutoCreate()">新建</button>
        <button type="button" class="btn sm ghost" @click="store.loadAutomations(true)">刷新</button>
      </div>
    </div>

    <div v-if="showCreate" class="auto-create">
      <div class="auto-sec-title">{{ CREATE_TITLE }}</div>
      <div class="ctrl-row">
        <label for="auto-new-name">名称</label>
        <input id="auto-new-name" v-model="newName" class="field" type="text" maxlength="100"
               placeholder="例如：客厅 有人移动-开灯">
      </div>
      <div class="ctrl-row">
        <label for="auto-new-template">模板</label>
        <select id="auto-new-template" class="field" :value="templateId" @change="onTemplateChange">
          <option v-if="!hasTemplate" value="">{{ NO_TEMPLATE }}</option>
          <option v-for="a in usable" :key="a.scene_id" :value="a.scene_id">
            {{ templateOptionText(a) }}
          </option>
        </select>
      </div>
      <div class="ctrl-row auto-form-check">
        <label><input v-model="newEnable" type="checkbox">
          创建后立即启用（默认停用，不勾选更安全）</label>
      </div>
      <div class="btn-wrap auto-form-actions">
        <button type="button" class="btn sm" title="只在本地生成，不会创建"
                @click="previewCreate">预览请求内容</button>
        <button type="button" class="btn sm danger" :disabled="!hasTemplate || store.autoBusy"
                @click="submitCreate">创建</button>
      </div>
      <pre v-if="createOut" class="auto-payload">{{ createOut }}</pre>
      <div class="dim-note">{{ CREATE_DANGER }}</div>
    </div>

    <div class="auto-list">
      <div v-for="a in items" :key="a.scene_id" class="auto-item"
           :class="a.enable ? 'on' : 'off'" @click="store.openAutoDetail(a.scene_id)">
        <span class="auto-dot"></span>
        <div class="auto-main">
          <div class="auto-name">{{ a.name }}</div>
          <div class="auto-sum">{{ a.summary }}</div>
        </div>
        <div class="auto-side">
          <span class="auto-badge">{{ a.enable ? '已启用' : '已停用' }}</span>
          <span class="auto-meta">{{ autoMeta(a) }}</span>
        </div>
      </div>
    </div>

    <div v-if="!items.length" class="auto-empty">
      <div class="auto-empty-k">{{ emptyText(store.autoHomeName) }}</div>
      <div class="dim-note">{{ EMPTY_HINT }}</div>
    </div>

    <div v-if="items.length" class="auto-note dim-note">{{ AUTO_NOTE }}</div>
  </section>
</template>
