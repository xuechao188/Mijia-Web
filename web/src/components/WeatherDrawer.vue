<script setup lang="ts">
/* 天气详情弹框：与旧 WeatherCard.drawer() 同源，完整读数 + 24 小时曲线
 * + 每 3 小时采样条 + 城市/尺寸设置。城市与尺寸都只存本机，不改后端配置。
 */
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import SparklineChart from './SparklineChart.vue'
import {
  SIZES, SIZE_LABELS, SIZE_TITLES, WEATHER_NOTE, WEATHER_FALLBACK,
  drawerReadouts, hourStrip, hourlyLabels, hourlySeries, iconSvg, kindOf,
  tempRange, tempText, weatherHero,
} from '../panels/weather'
import { usePanelsStore } from '../stores/panels'

const store = usePanelsStore()
const w = computed(() => store.weather || WEATHER_FALLBACK)
const icon = computed(() => iconSvg(kindOf(w.value && w.value.code), 40))
const readouts = computed(() => drawerReadouts(w.value))
const points = computed(() => hourlySeries(w.value))
const labels = computed(() => hourlyLabels(w.value))
const range = computed(() => tempRange(w.value))
const tempFormat = (v: number): string => tempText(v, 0) + '°'
const hours = computed(() => hourStrip(w.value))
const rangeText = computed(() =>
  tempText(range.value.min, 0) + '° / ' + tempText(range.value.max, 0) + '°')
const cityInput = ref(store.weatherCity)

watch(() => store.weatherCity, (v) => { cityInput.value = v })

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') store.closeWeatherDrawer()
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="drawer-layer">
    <div class="drawer-mask" @click="store.closeWeatherDrawer()"></div>
    <div class="sheet m-glass m-glass-strong" role="dialog" aria-modal="true"
         aria-label="天气详情">
      <header class="sheet-head">
        <div>
          <h3>天气</h3>
          <span class="sheet-cat mono">{{ w.city || '当前城市' }}</span>
        </div>
        <button type="button" class="btn sm ghost" aria-label="关闭"
                @click="store.closeWeatherDrawer()">
          <svg class="ui-ico" viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </header>

      <div class="sheet-body">
        <!-- 左列：当前读数与城市 / 尺寸设置 -->
        <div class="sheet-col">
          <section class="dr-panel m-surface">
            <div class="wc-hero">
              <span class="wc-glyph big" v-html="icon"></span>
              <div class="wc-hero-text">
                <div class="wc-hero-temp">{{ tempText(w.temp, 0) }}°</div>
                <div class="wc-hero-sub">{{ weatherHero(w) }}</div>
              </div>
            </div>
            <div class="dr-readouts">
              <div v-for="r in readouts" :key="r.label" class="dr-readout"
                   :class="{ primary: r.primary }">
                <span class="dr-readout-k">{{ r.label }}</span>
                <span class="dr-readout-v">{{ r.value }}</span>
              </div>
            </div>
          </section>

          <section class="dr-panel m-surface wc-settings">
            <div class="ctrl-row">
              <label for="wc-city">天气城市</label>
              <div class="ctrl-line">
                <input id="wc-city" v-model="cityInput" class="field" type="text"
                       placeholder="留空使用服务器默认城市">
              </div>
              <div class="btn-wrap wc-city-actions">
                <button type="button" class="btn sm" @click="store.setWeatherCity(cityInput.trim())">保存</button>
                <button type="button" class="btn sm ghost" @click="store.setWeatherCity('')">恢复默认</button>
                <button type="button" class="btn sm ghost" @click="store.loadWeather()">刷新天气</button>
              </div>
            </div>
            <div class="ctrl-row">
              <label>卡片尺寸</label>
              <div class="wc-sizes in-drawer">
                <button v-for="s in SIZES" :key="s" type="button" class="wc-size"
                        :class="{ active: s === store.weatherSize }" :title="SIZE_TITLES[s]"
                        @click="store.setWeatherSize(s)">{{ SIZE_LABELS[s] }}</button>
              </div>
            </div>
            <div class="dim-note wc-note">{{ WEATHER_NOTE }}</div>
          </section>
        </div>

        <!-- 右列：24 小时温度曲线与逐时采样 -->
        <div class="sheet-col">
          <section class="dr-panel m-surface">
            <div class="dr-history-head">
              <span class="dr-h-label">24 小时温度</span>
              <span class="dim-note">{{ points.length }} 个采样点</span>
            </div>
            <div class="wc-chart">
              <div v-if="!points.length" class="ct-chart-empty">暂无逐时预报数据</div>
              <template v-else>
                <div class="ct-chart-cap">
                  <span>未来 {{ (w.hourly || []).length }} 小时 · {{ labels[0] }} 起</span>
                  <span class="ct-chart-last">{{ rangeText }}</span>
                </div>
                <div class="ct-chart-svg tall">
                  <SparklineChart :points="points" :format="tempFormat" time-mode="index"
                                  :labels="labels" :w="320" :h="68" color="var(--accent)" />
                </div>
                <div class="ct-chart-cap">
                  <span>{{ labels[0] }}</span><span>{{ labels[1] }}</span>
                </div>
              </template>
            </div>
            <div v-if="hours.length" class="wc-hours">
              <div v-for="(h, i) in hours" :key="i" class="wc-hour">
                <span class="wc-hour-t">{{ h.time }}</span>
                <span class="wc-hour-v">{{ h.temp }}</span>
                <span class="wc-hour-p">{{ h.pop }}</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>
