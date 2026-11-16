<script setup lang="ts">
/* 红外遥控面板（详情弹框左列）。
 *
 * 红外是**单向发码**：没有状态可读，按下去就是对着家电发一次红外。
 * 所以这里不摆开关、不做选中态、不显示「已开启」——只把命令按用途分组
 * 排好，点一下就发；自定义遥控的按键表另起一块，铺成网格。
 *
 * 两类设备共用这一个面板：
 *   - 品类遥控（电视/机顶盒/空调/灯具）：source 是 spec 动作与只写属性
 *   - 自定义遥控（米家里自己配的遥控器）：source 是云端按键表
 * 两者都为空时如实说明「米家侧还没有配置按键」，不假装能点。
 *
 * 空调温度是一个「－ 26°C ＋」步进，不是十几个 °C 按钮：温度是连续量，
 * 铺成按钮既占版面又要横着找。± 挪的是**本机最后一次发送**的值，因为
 * ir-temperature 只写不读，云端拿不到当前温度。
 */
import { computed, ref, watch } from 'vue'
import type { IrCmd, IrInfo } from '../devices/types'
import { useDevicesStore } from '../stores/devices'

const props = defineProps<{ did: string; ir: IrInfo; offline?: boolean }>()
const store = useDevicesStore()

type Row =
  | { kind: 'cmds'; name: string; items: IrCmd[] }
  | { kind: 'temp' }

/* 后端已经按「电源 → 模式 → 风速…」排好序，这里只做相邻归组，不再重排。
 * 温度块插在「模式」之后（没有模式就排在电源组之后），和实体遥控器的
 * 键位一致：电源、模式、温度、风速。 */
const TEMP_AFTER = ['模式', '电源']

const rows = computed<Row[]>(() => {
  const out: Row[] = []
  const hasTemp = Boolean(props.ir.temp)
  let placed = !hasTemp
  const putTemp = () => { out.push({ kind: 'temp' }); placed = true }

  for (const c of props.ir.cmds || []) {
    const name = c.group || '其他'
    if (!placed && !TEMP_AFTER.includes(name)
        && out.some((r) => r.kind === 'cmds' && TEMP_AFTER.includes(r.name))) {
      putTemp()
    }
    const last = out[out.length - 1]
    if (last && last.kind === 'cmds' && last.name === name) last.items.push(c)
    else out.push({ kind: 'cmds', name, items: [c] })
  }
  if (!placed) putTemp()
  return out
})
const keys = computed(() => props.ir.keys || [])
const empty = computed(() => !rows.value.length && !keys.value.length)
/* 模式是有限枚举，格子按组名切换密度 */
const dense = (name: string): boolean => name === '模式'

/* ---------------- 温度步进 ---------------- */
const temp = computed(() => props.ir.temp || null)
const tempKey = (did: string): string => 'ir-temp:' + did

function storedTemp(): number | null {
  const t = props.ir.temp
  if (!t) return null
  let raw = NaN
  try { raw = Number(localStorage.getItem(tempKey(props.did))) } catch { /* 隐私模式 */ }
  if (!Number.isFinite(raw)) return null
  return raw >= t.min && raw <= t.max ? raw : null
}

const tempVal = ref(26)
/* 发一次是一次网络往返：期间锁住两个键，连点不会把绝对值发乱序
   （否则后发先至，界面数字和云端收到的最后一个值会对不上）。 */
const busy = ref(false)
function loadTemp(): void {
  const t = props.ir.temp
  if (!t) return
  tempVal.value = storedTemp() ?? t.default
}
watch(() => [props.did, props.ir.temp], loadTemp, { immediate: true })

const canDown = computed(() => {
  const t = temp.value
  return Boolean(t) && !props.offline && !busy.value && tempVal.value > t!.min
})
const canUp = computed(() => {
  const t = temp.value
  return Boolean(t) && !props.offline && !busy.value && tempVal.value < t!.max
})

async function step(dir: 1 | -1): Promise<void> {
  const t = temp.value
  if (!t || props.offline || busy.value) return
  const stepLen = t.step || 1
  const next = Math.min(t.max, Math.max(t.min, tempVal.value + dir * stepLen))
  if (next === tempVal.value) return
  busy.value = true
  try {
    const sent = await store.setIrTemp(props.did, next)
    if (!sent) return
    tempVal.value = next
    try { localStorage.setItem(tempKey(props.did), String(next)) } catch { /* 忽略 */ }
  } finally {
    busy.value = false
  }
}

function run(cmd: IrCmd): void {
  if (props.offline) return
  void store.pressIr(props.did, cmd)
}
function press(keyId: number | string, label: string): void {
  if (props.offline) return
  void store.pressIrKey(props.did, keyId, label)
}
</script>

<template>
  <section class="dr-panel m-surface ir-panel">
    <div class="dr-section-label">遥控</div>

    <template v-for="(row, i) in rows" :key="row.kind === 'temp' ? 'temp' : 'g' + row.name + i">
      <div v-if="row.kind === 'temp'" class="ir-group">
        <div class="ir-group-k">温度<span class="ir-count">· 本机记录</span></div>
        <div class="ir-temp">
          <button type="button" class="ir-step" :disabled="!canDown"
                  aria-label="降低 1 度" @click="step(-1)">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.4 8h9.2" /></svg>
          </button>
          <div class="ir-temp-v">{{ tempVal }}<span>°C</span></div>
          <button type="button" class="ir-step" :disabled="!canUp"
                  aria-label="升高 1 度" @click="step(1)">
            <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M3.4 8h9.2M8 3.4v9.2" /></svg>
          </button>
        </div>
      </div>
      <div v-else class="ir-group">
        <div class="ir-group-k">{{ row.name }}</div>
        <div class="btn-wrap ir-btns" :class="{ dense: dense(row.name) }">
          <button v-for="c in row.items" :key="c.id" type="button"
                  class="btn sm ir-btn" :disabled="offline"
                  @click="run(c)">{{ c.label }}</button>
        </div>
      </div>
    </template>

    <template v-if="keys.length">
      <div class="ir-group">
        <div class="ir-group-k">自定义按键<span class="ir-count">{{ keys.length }} 个</span></div>
        <div class="ir-keys">
          <button v-for="k in keys" :key="String(k.id)" type="button"
                  class="btn sm ir-key" :disabled="offline"
                  :title="k.name" @click="press(k.id, k.name)">{{ k.name }}</button>
        </div>
      </div>
    </template>

    <div v-if="empty" class="dim-note">
      这台遥控器在米家侧还没有可用的按键。先在米家 App 里给它配好按键，再回来刷新。
    </div>
    <div v-else-if="offline" class="dim-note">
      设备离线：红外发射器（一般是小爱音箱）不在线，指令发不出去。
    </div>
    <div v-if="ir.note && !empty" class="dim-note">{{ ir.note }}</div>
  </section>
</template>
