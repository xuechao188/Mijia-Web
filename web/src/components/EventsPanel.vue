<script setup lang="ts">
/* 事件流：与旧界面 #event-panel 同源，最近 50 条；正文一律插值，不拼 HTML。 */
import { EVENT_EMPTY, EVENT_TITLE, eventText, eventTime, eventTone } from '../panels/events'
import { usePanelsStore } from '../stores/panels'

const store = usePanelsStore()
</script>

<template>
  <section class="event-panel m-surface">
    <div class="dr-history-head">
      <span class="dr-h-label">{{ EVENT_TITLE }}</span>
      <span class="dim-note mono">{{ store.events.length }} 条</span>
    </div>
    <div v-if="!store.events.length" class="dim-note event-empty">{{ EVENT_EMPTY }}</div>
    <ul v-else class="event-list">
      <li v-for="(e, i) in store.events" :key="i" :class="eventTone(e)">
        <span class="t mono">{{ eventTime(e) }}</span>
        <span class="event-text">{{ eventText(e) }}</span>
      </li>
    </ul>
  </section>
</template>
