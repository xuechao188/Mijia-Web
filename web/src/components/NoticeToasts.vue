<script setup lang="ts">
/* 右下角通知卡片：来了新设备通知就压一张，最多 3 张，9 秒自己收。
 * 纯展示，点击交给 store（清未读 + 若能对上设备就开详情）。 */
import { noticeAge, noticeKind, noticeSub, noticeTitle, noticeTone } from '../panels/notices'
import { useNoticesStore } from '../stores/notices'

const store = useNoticesStore()
</script>

<template>
  <div v-if="store.toasts.length" class="nt-stack" role="status" aria-live="polite">
    <div v-for="n in store.toasts" :key="n.msg_id" class="nt-card m-glass m-glass-strong"
         :class="noticeTone(n)">
      <button type="button" class="nt-x" aria-label="关闭" @click="store.dismiss(n.msg_id)">
        <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
      </button>
      <div class="nt-card-hd">
        <span class="nt-card-kind">{{ noticeKind(n) }}</span>
        <span class="nt-card-time mono">{{ noticeAge(n.ts) || n.time }}</span>
      </div>
      <div class="nt-card-title" @click="store.openToast(n)">{{ noticeTitle(n) }}</div>
      <div class="nt-card-sub">{{ noticeSub(n) }}</div>
      <div v-if="store.perm === 'default'" class="nt-card-ask">
        <button type="button" class="btn sm ghost" @click.stop="store.requestPerm()">
          开启系统通知
        </button>
      </div>
      <div v-else-if="store.perm === 'denied'" class="nt-card-ask mono">
        系统通知已被浏览器屏蔽
      </div>
    </div>
  </div>
</template>
