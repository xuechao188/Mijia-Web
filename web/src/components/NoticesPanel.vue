<script setup lang="ts">
/* 设备通知面板：米家消息中心的未读消息（门铃、门锁、电量、耗材…）。
 * 只读云端，不替用户在手机上标已读；本地「已读」只影响这个界面的红点。 */
import { computed, ref } from 'vue'
import {
  NOTICE_EMPTY, NOTICE_FILTERS, NOTICE_HINT, NOTICE_PERM_ASK_DEFAULT,
  NOTICE_PERM_DENIED, NOTICE_PERM_OFF, NOTICE_PERM_ON, NOTICE_SYSTEM_UNAVAILABLE,
  NOTICE_TITLE, filterNotices, formatDiag, noticeAge, noticeCounts, noticeKind,
  noticeSub, noticeTitle, noticeTone, type NoticeFilter,
} from '../panels/notices'
import { useNoticesStore } from '../stores/notices'

const store = useNoticesStore()

/* 标签筛选：默认「全部」，只影响本页展示，不改后端数据或已读状态。 */
const activeFilter = ref<NoticeFilter>('all')
const counts = computed(() => noticeCounts(store.list))
const visible = computed(() => filterNotices(store.list, activeFilter.value))
const filterEmpty = computed(() => NOTICE_FILTERS.find((f) => f.key === activeFilter.value)?.label || '')

const permText = computed(() => {
  if (store.perm === 'unsupported') return NOTICE_SYSTEM_UNAVAILABLE
  if (store.perm === 'denied') return NOTICE_PERM_DENIED
  if (store.perm === 'granted') return NOTICE_PERM_ON
  // 点过「开启」却仍是 default：Edge 静默拒绝，给出手动开启引导
  if (store.permAsked) return NOTICE_PERM_ASK_DEFAULT
  return NOTICE_PERM_OFF
})
const canAsk = computed(() => store.perm === 'default')

const copied = ref(false)
async function copyDiag(): Promise<void> {
  if (!store.diag) return
  const text = formatDiag(store.diag)
  try {
    await navigator.clipboard.writeText(text)
  } catch {
    // 非安全上下文或旧浏览器可能没有剪贴板 API，退回选中文本由用户手动复制
    const el = document.getElementById('nt-diag-text')
    if (el) {
      const range = document.createRange()
      range.selectNodeContents(el)
      const sel = window.getSelection()
      sel?.removeAllRanges()
      sel?.addRange(range)
    }
  }
  copied.value = true
  setTimeout(() => { copied.value = false }, 1800)
}
</script>

<template>
  <section class="event-panel m-surface nt-panel">
    <div class="dr-history-head">
      <span class="dr-h-label">{{ NOTICE_TITLE }}</span>
      <span class="dim-note mono">{{ store.unread }} 条未读 · 共 {{ store.list.length }} 条</span>
      <div class="nt-actions">
        <button v-if="canAsk" type="button" class="btn sm" @click="store.requestPerm()">
          开启浏览器通知
        </button>
        <button type="button" class="btn sm ghost" :disabled="store.diagBusy"
                @click="store.runTest()">
          {{ store.diagBusy ? '检测中…' : '测试通知' }}
        </button>
        <button type="button" class="btn sm ghost" :disabled="store.loading"
                @click="store.refresh()">
          {{ store.loading ? '检查中…' : '立即检查' }}
        </button>
        <button type="button" class="btn sm ghost" :disabled="!store.hasUnread"
                @click="store.markAll()">全部已读</button>
      </div>
    </div>

    <!-- 默认态不写这句：右边就是「开启浏览器通知」按钮，重复一遍只是噪音。
         点过后即使仍是 default 也显示，把 Edge 的静默拒绝讲清楚。 -->
    <p v-if="store.perm !== 'default' || store.permAsked" class="nt-perm"
       :class="{ off: store.perm === 'denied' || store.perm === 'unsupported' }">
      {{ permText }}
    </p>

    <!-- 测试通知的诊断结果：结论醒目、详情可复制，便于反馈 -->
    <div v-if="store.diag" class="nt-diag">
      <div class="nt-diag-hd">
        <span class="nt-diag-title">通知自检结果</span>
        <button type="button" class="btn sm ghost" @click="copyDiag">
          {{ copied ? '已复制' : '复制诊断' }}
        </button>
      </div>
      <p class="nt-diag-verdict">{{ store.diag.verdict }}</p>
      <pre id="nt-diag-text" class="nt-diag-detail">{{ formatDiag(store.diag) }}</pre>
    </div>

    <!-- 类型标签：单选，带每类条数；只筛本页列表，不改未读数 -->
    <div class="nt-filter" role="group" aria-label="按类型筛选通知">
      <button v-for="f in NOTICE_FILTERS" :key="f.key" type="button"
              class="chip" :class="{ active: activeFilter === f.key }"
              :aria-pressed="activeFilter === f.key"
              @click="activeFilter = f.key">
        {{ f.label }} <span class="mono">{{ counts[f.key] }}</span>
      </button>
    </div>

    <div v-if="!store.list.length" class="dim-note event-empty">{{ NOTICE_EMPTY }}</div>
    <div v-else-if="!visible.length" class="dim-note event-empty">
      当前没有「{{ filterEmpty }}」类型的通知。
    </div>
    <ul v-else class="event-list nt-list">
      <li v-for="n in visible" :key="n.msg_id" :class="[noticeTone(n), { 'is-new': !n.seen }]"
          @click="store.openNotice(n)">
        <span class="nt-dot" aria-hidden="true"></span>
        <span class="nt-main">
          <span class="nt-title">{{ noticeTitle(n) }}</span>
          <span class="nt-sub">{{ noticeSub(n) }}</span>
        </span>
        <span class="nt-kind">{{ noticeKind(n) }}</span>
        <span class="t mono">{{ noticeAge(n.ts) || n.time }}</span>
      </li>
    </ul>

    <p class="dim-note nt-hint">{{ NOTICE_HINT }}</p>
    <p v-if="store.err" class="dim-note nt-err">上次拉取失败：{{ store.err }}</p>
  </section>
</template>
