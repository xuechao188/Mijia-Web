<script setup lang="ts">
/* 关于应用 / 在线升级弹窗。
 *
 * 从顶栏版本号点进来，讲清三件事：当前版本与仓库地址、有没有新版本、
 * 升级/回滚的进度。检测与升级全走 update store，弹窗只负责呈现与交互。
 * 升级成功后若后端开了自动重启，倒计时期间不断探测 /api/ping，
 * 后端一恢复就整页刷新，让新的前后端代码立刻生效。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { dialogEnter, dialogLeave } from '../motion'
import { useUpdateStore, type Release } from '../stores/update'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

const update = useUpdateStore()
const shown = ref(props.open)
const refreshing = ref(false)

watch(() => props.open, (v) => {
  shown.value = v
  if (v) {
    void update.bootstrap()
    update.reset()
  }
})

const busy = computed(() => update.busy !== '')
const homepage = computed(() => update.info?.homepage || '')
const version = computed(() => update.info?.version || '')
const latest = computed<Release | undefined>(() => update.checkResult?.latest)

function fmtSize(n: number): string {
  if (!n) return ''
  return n >= 1024 * 1024
    ? (n / 1024 / 1024).toFixed(1) + ' MB'
    : Math.ceil(n / 1024) + ' KB'
}
function fmtDate(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleDateString('zh-CN')
}

function onEnter(el: Element): void { dialogEnter(el) }
function onLeave(el: Element, done: () => void): void { dialogLeave(el, done) }
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape' && shown.value && !busy.value) emit('close')
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => {
  window.removeEventListener('keydown', onKey)
  if (probeTimer) clearInterval(probeTimer)
})

let probeTimer: ReturnType<typeof setInterval> | null = null
let probes = 0

/* 升级/回滚成功后：若会自动重启，探测后端恢复再刷新整页。 */
watch(() => update.note, () => {
  const res = update.checkResult
  void res
  const restarting = /正在重启|即将刷新/.test(update.note)
  if (!restarting || probeTimer) return
  refreshing.value = true
  probes = 0
  // 先给后端 2 秒关机时间，之后每 1.5 秒探一次，最多约 40 秒
  setTimeout(() => {
    probeTimer = setInterval(async () => {
      probes += 1
      try {
        const r = await fetch('/api/update/info')
        if (r.ok) {
          if (probeTimer) clearInterval(probeTimer)
          probeTimer = null
          window.location.reload()
        }
      } catch { /* 还没起来，继续等 */ }
      if (probes > 26 && probeTimer) {
        clearInterval(probeTimer)
        probeTimer = null
        refreshing.value = false
      }
    }, 1500)
  }, 2000)
})
</script>

<template>
  <Transition :css="false" @enter="onEnter" @leave="onLeave">
    <div v-if="shown" class="cap-layer" role="dialog" aria-modal="true" aria-label="关于应用">
      <div class="cap-mask" @click="!busy && emit('close')"></div>
      <div class="cap-box about m-glass m-glass-strong">
        <header class="cap-head">
          <span class="about-mark" aria-hidden="true">米</span>
          <h4>关于应用</h4>
          <button type="button" class="icon-btn cap-x" aria-label="关闭"
                  :disabled="busy" @click="emit('close')">
            <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
          </button>
        </header>

        <div class="about-body">
          <div class="about-ver">
            <span class="about-ver-label">当前版本</span>
            <span class="about-ver-num mono">v{{ version }}</span>
          </div>

          <div class="about-row">
            <span class="about-key">项目地址</span>
            <a v-if="homepage" class="about-link" :href="homepage"
               target="_blank" rel="noopener noreferrer">{{ homepage }}</a>
            <span v-else class="about-muted">未配置（设置 MIHOME_UPDATE_REPO 后可用）</span>
          </div>

          <div class="about-actions">
            <button type="button" class="btn sm" :disabled="busy"
                    @click="update.check()">
              {{ update.busy === 'check' ? '检测中…' : '检测新版本' }}
            </button>
            <button v-if="update.checkResult?.has_update" type="button" class="btn sm active"
                    :disabled="busy" @click="update.apply()">
              {{ update.busy === 'apply' ? '升级中…' : '下载并升级' }}
            </button>
          </div>

          <div v-if="update.note" class="about-note" :class="update.noteTone">
            {{ refreshing ? '升级完成，正在等待服务重启并刷新页面…' : update.note }}
          </div>

          <!-- 新版本详情 -->
          <div v-if="latest" class="about-release">
            <div class="about-rel-head">
              <span class="about-rel-tag mono">{{ latest.tag }}</span>
              <span v-if="latest.published_at" class="about-rel-date">{{ fmtDate(latest.published_at) }}</span>
            </div>
            <div v-if="latest.name" class="about-rel-name">{{ latest.name }}</div>
            <div v-if="latest.asset" class="about-rel-asset">
              升级包 {{ latest.asset.name }} · {{ fmtSize(latest.asset.size) }}
            </div>
            <pre v-if="latest.body" class="about-rel-body">{{ latest.body }}</pre>
          </div>

          <!-- 升级历史 / 回滚 -->
          <div v-if="update.info?.last && Object.keys(update.info.last).length"
               class="about-history">
            <div class="about-key">最近一次升级</div>
            <div class="about-hist-line">
              v{{ String(update.info.last.from || '') }} → v{{ String(update.info.last.to || '') }}
            </div>
            <button v-if="update.info.backups?.length" type="button"
                    class="btn sm ghost" :disabled="busy" @click="update.rollback()">
              {{ update.busy === 'rollback' ? '回滚中…' : '回滚到升级前' }}
            </button>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.about { width: min(520px, calc(100vw - 32px)); }
.about-mark {
  width: 26px; height: 26px; border-radius: 8px; flex: none;
  display: grid; place-items: center;
  background: var(--blue); color: #fff; font-size: 14px; font-weight: 700;
}
.about-body { display: flex; flex-direction: column; gap: 16px; padding-top: 4px; }
.about-ver {
  display: flex; align-items: baseline; gap: 12px;
  padding: 14px 16px; border-radius: var(--r-md); background: var(--pill-bg);
}
.about-ver-label { font-size: 12px; color: var(--ink-muted); }
.about-ver-num { font-size: 22px; font-weight: 600; color: var(--ink); }
.about-row { display: flex; flex-direction: column; gap: 5px; }
.about-key { font-size: 12px; color: var(--ink-muted); }
.about-link {
  font-size: 13px; color: var(--blue); word-break: break-all;
  text-decoration: none;
}
.about-link:hover { text-decoration: underline; }
.about-muted { font-size: 13px; color: var(--ink-muted); }
.about-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.about-note {
  font-size: 12px; padding: 9px 12px; border-radius: var(--r-xs);
  background: var(--pill-bg); color: var(--ink-soft);
}
.about-note.ok { color: var(--lime); }
.about-note.warn { color: var(--red-text); }
.about-release {
  border-top: 1px solid var(--edge); padding-top: 14px;
  display: flex; flex-direction: column; gap: 6px;
}
.about-rel-head { display: flex; align-items: center; gap: 10px; }
.about-rel-tag { font-size: 13px; font-weight: 600; color: var(--blue); }
.about-rel-date { font-size: 11px; color: var(--ink-faint); }
.about-rel-name { font-size: 13px; color: var(--ink); }
.about-rel-asset { font-size: 11px; color: var(--ink-muted); }
.about-rel-body {
  margin: 4px 0 0; padding: 10px 12px; border-radius: var(--r-xs);
  background: var(--pill-bg); color: var(--ink-soft);
  font-size: 12px; line-height: 1.6; white-space: pre-wrap; word-break: break-word;
  max-height: 180px; overflow: auto;
  font-family: inherit;
}
.about-history {
  border-top: 1px solid var(--edge); padding-top: 14px;
  display: flex; flex-direction: column; gap: 8px; align-items: flex-start;
}
.about-hist-line { font-size: 13px; color: var(--ink); }
</style>
