<script setup lang="ts">
/* 设备通知面板：米家消息中心的未读消息（门铃、门锁、电量、耗材…）。
 * 只读云端，不替用户在手机上标已读；本地「已读」只影响这个界面的红点。 */
import { computed } from 'vue'
import {
  NOTICE_EMPTY, NOTICE_HINT, NOTICE_PERM_DENIED, NOTICE_PERM_OFF, NOTICE_PERM_ON,
  NOTICE_SYSTEM_UNAVAILABLE, NOTICE_TITLE, noticeAge, noticeKind, noticeSub,
  noticeTitle, noticeTone,
} from '../panels/notices'
import { useNoticesStore } from '../stores/notices'

const store = useNoticesStore()

const permText = computed(() => {
  if (store.perm === 'unsupported') return NOTICE_SYSTEM_UNAVAILABLE
  if (store.perm === 'denied') return NOTICE_PERM_DENIED
  return store.perm === 'granted' ? NOTICE_PERM_ON : NOTICE_PERM_OFF
})
const canAsk = computed(() => store.perm === 'default')
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
        <button type="button" class="btn sm ghost" :disabled="store.loading"
                @click="store.refresh()">
          {{ store.loading ? '检查中…' : '立即检查' }}
        </button>
        <button type="button" class="btn sm ghost" :disabled="!store.hasUnread"
                @click="store.markAll()">全部已读</button>
      </div>
    </div>

    <!-- 默认态不写这句：右边就是「开启浏览器通知」按钮，重复一遍只是噪音 -->
    <p v-if="store.perm !== 'default'" class="nt-perm"
       :class="{ off: store.perm === 'denied' || store.perm === 'unsupported' }">
      {{ permText }}
    </p>

    <div v-if="!store.list.length" class="dim-note event-empty">{{ NOTICE_EMPTY }}</div>
    <ul v-else class="event-list nt-list">
      <li v-for="n in store.list" :key="n.msg_id" :class="[noticeTone(n), { 'is-new': !n.seen }]"
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
