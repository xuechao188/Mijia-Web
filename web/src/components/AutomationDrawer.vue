<script setup lang="ts">
/* 自动化详情弹框：旧界面复用的 #drawer 里 syncAutomationDrawer 那一套。
 * 改名 / 启停 / 删除都先二次确认，删除还要完整输入名称复核；
 * 所有写请求由 panels store 统一带 confirm=true。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  DELETE_SECTION_TEXT, DELETE_SECTION_TITLE, EDIT_HINT, EDIT_READONLY,
  EDIT_TITLE, NAME_EMPTY, NAME_MISMATCH, NAME_SAME, PREVIEW_NEED_CHANGE, RAW_SUMMARY,
  applyConfirmText, applyOutput, deleteConfirmText, deleteOutput, detailBlocks,
  detailHead, entryDevice, entryName, entryValue, previewOutput,
} from '../panels/automations'
import { usePanelsStore } from '../stores/panels'

const store = usePanelsStore()
const item = computed(() => store.autoDetail)
const nameInput = ref('')
const deleteInput = ref('')
const editOut = ref(EDIT_HINT)
const deleteOut = ref('')
const blocks = computed(() => item.value ? detailBlocks(item.value) : [])
const rawText = computed(() => item.value ? JSON.stringify(item.value.raw, null, 2) : '')
const headText = computed(() => item.value ? detailHead(item.value) : '')

watch(item, (v) => {
  nameInput.value = v ? v.name : ''
  deleteInput.value = ''
  editOut.value = store.autoWritable ? EDIT_HINT : EDIT_READONLY
  deleteOut.value = ''
})

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') store.closeAutoDetail()
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

function patchName(): { name: string } | Record<string, never> {
  const name = nameInput.value.trim()
  return name && item.value && name !== item.value.name ? { name } : {}
}

async function previewEdit(): Promise<void> {
  if (!item.value) return
  /* 没有改动就没有 payload 可预览：这一步先拦住，别让后端拿「patch 必须非空」当答复。 */
  const patch = patchName()
  if (!Object.keys(patch).length) {
    editOut.value = PREVIEW_NEED_CHANGE
    return
  }
  editOut.value = '正在生成本地预览…'
  const r = await store.previewEdit(item.value.scene_id, patch)
  editOut.value = previewOutput(r as { ok: boolean; error?: string; preview?: unknown })
}

async function saveName(): Promise<void> {
  const cur = item.value
  if (!cur) return
  const name = nameInput.value.trim()
  if (!name) { store.toast(NAME_EMPTY); return }
  if (name === cur.name) { store.toast(NAME_SAME); return }
  if (!window.confirm(applyConfirmText({ name }))) return
  editOut.value = '正在写入米家云端…'
  const r = await store.applyEdit(cur, { name })
  editOut.value = applyOutput(r as {
    ok: boolean; error?: string; result?: unknown; preview?: { changes?: unknown }
  })
}

async function toggleEnable(): Promise<void> {
  const cur = item.value
  if (!cur) return
  const enable = !cur.enable
  if (!window.confirm(applyConfirmText({ enable }))) return
  editOut.value = '正在写入米家云端…'
  const r = await store.applyEdit(cur, { enable })
  editOut.value = applyOutput(r as {
    ok: boolean; error?: string; result?: unknown; preview?: { changes?: unknown }
  })
}

async function previewDelete(): Promise<void> {
  const cur = item.value
  if (!cur) return
  deleteOut.value = '正在本地生成…'
  const r = await store.previewDelete(cur.scene_id, deleteInput.value.trim())
  deleteOut.value = r.ok
    ? JSON.stringify(r.preview, null, 2)
    : '生成失败：' + (r.error || '未知错误')
}

async function doDelete(): Promise<void> {
  const cur = item.value
  if (!cur) return
  const name = deleteInput.value.trim()
  if (name !== cur.name) { store.toast(NAME_MISMATCH); return }
  if (!window.confirm(deleteConfirmText(cur.name))) return
  deleteOut.value = '正在从米家云端删除…'
  const r = await store.deleteAutomation(cur, name)
  if (!r.ok) deleteOut.value = deleteOutput(r as { ok: boolean; error?: string })
}
</script>

<template>
  <div class="drawer-layer">
    <div class="drawer-mask" @click="store.closeAutoDetail()"></div>
    <div class="sheet m-glass m-glass-strong" role="dialog" aria-modal="true"
         aria-label="自动化详情">
      <header class="sheet-head">
        <div>
          <h3>自动化详情</h3>
          <span class="sheet-cat mono">{{ headText }}</span>
        </div>
        <button type="button" class="btn sm ghost" aria-label="关闭"
                @click="store.closeAutoDetail()">
          <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </header>

      <div class="sheet-body">
        <div v-if="!item" class="dim-note">正在读取自动化详情…</div>

        <template v-else>
          <!-- 左列：只读的触发与动作明细 -->
          <div class="sheet-col">
            <section class="dr-panel m-surface">
              <div class="auto-detail-title">{{ item.name }}</div>
              <template v-for="b in blocks" :key="b[0]">
                <div v-if="b[1].length" class="auto-sec">
                  <div class="auto-sec-title">{{ b[0] }} · {{ b[1].length }}</div>
                  <div v-for="(e, i) in b[1]" :key="i" class="auto-row">
                    <span class="auto-row-dev">{{ entryDevice(e) }}</span>
                    <span class="auto-row-name">{{ entryName(e) }}</span>
                    <span v-if="entryValue(e)" class="auto-row-val">{{ entryValue(e) }}</span>
                  </div>
                </div>
              </template>
              <div class="auto-summary">{{ item.summary }}</div>
              <details class="auto-raw">
                <summary>{{ RAW_SUMMARY }}</summary>
                <pre>{{ rawText }}</pre>
              </details>
            </section>
          </div>

          <!-- 右列：写入（改名 / 启停）与删除 -->
          <div class="sheet-col">
            <section class="dr-panel m-surface auto-edit">
              <div class="auto-sec-title">{{ EDIT_TITLE }}</div>
              <div class="ctrl-row">
                <label for="auto-edit-name">名称</label>
                <div class="ctrl-line">
                  <input id="auto-edit-name" v-model="nameInput" class="field" type="text">
                  <button type="button" class="btn sm" :disabled="!store.autoWritable || store.autoBusy"
                          @click="saveName">保存名称</button>
                </div>
              </div>
              <div class="ctrl-row">
                <label>状态</label>
                <div class="btn-wrap">
                  <button type="button" class="btn sm" :disabled="!store.autoWritable || store.autoBusy"
                          @click="toggleEnable">{{ item.enable ? '停用此自动化' : '启用此自动化' }}</button>
                  <button type="button" class="btn sm ghost" title="只在本地生成，不会写入米家"
                          @click="previewEdit">预览请求内容</button>
                </div>
              </div>
              <pre class="auto-payload">{{ editOut }}</pre>
            </section>

            <section v-if="store.autoDeleteSupported" class="dr-panel m-surface auto-danger">
              <div class="auto-sec-title">{{ DELETE_SECTION_TITLE }}</div>
              <div class="auto-danger-text">{{ DELETE_SECTION_TEXT }}</div>
              <div class="ctrl-row">
                <label for="auto-delete-name">复核</label>
                <div class="ctrl-line">
                  <input id="auto-delete-name" v-model="deleteInput" class="field" type="text"
                         :placeholder="item.name">
                </div>
                <div class="btn-wrap auto-danger-actions">
                  <button type="button" class="btn sm ghost" title="只在本地生成，不会删除"
                          @click="previewDelete">预览请求内容</button>
                  <button type="button" class="btn sm danger" :disabled="store.autoBusy"
                          @click="doDelete">删除此自动化</button>
                </div>
              </div>
              <pre class="auto-payload">{{ deleteOut }}</pre>
            </section>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>
