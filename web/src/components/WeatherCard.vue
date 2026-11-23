<script setup lang="ts">
/* 天气卡：与旧 WeatherCard.render() 同源，三尺寸信息预算、图标与脚注一致。
 * 只把 DOM 拼装换成模板；v-html 仅用于本地常量生成的 SVG 字符串。
 */
import { computed } from 'vue'
import SparklineChart from './SparklineChart.vue'
import {
  FIELDS, SIZES, SIZE_LABELS, SIZE_TITLES, fieldsFor, hourlyLabels,
  hourlySeries, iconSvg, kindOf, tempRange, tempText, weatherCardClass,
  weatherFoot, weatherMetrics,
} from '../panels/weather'
import type { WeatherData, WeatherSize } from '../panels/types'
import { usePanelsStore } from '../stores/panels'

const props = defineProps<{ w: WeatherData | null; size: WeatherSize }>()
const store = usePanelsStore()

const fields = computed(() =>
  props.w && props.w.unavailable ? FIELDS.sm.slice() : fieldsFor(props.size))
const kind = computed(() => kindOf(props.w && props.w.code))
const icon = computed(() => iconSvg(kind.value, 22))
const metrics = computed(() => weatherMetrics(props.w, fields.value))
const hasHourly = computed(() => fields.value.includes('hourly'))
const points = computed(() => hourlySeries(props.w))
const labels = computed(() => hourlyLabels(props.w))
const range = computed(() => tempRange(props.w))
const tempFormat = (v: number): string => tempText(v, 0) + '°'
const chartCap = computed(() =>
  '未来 ' + ((props.w && props.w.hourly) || []).length + ' 小时 · ' + labels.value[0] + ' 起')
const rangeText = computed(() =>
  tempText(range.value.min, 0) + '° / ' + tempText(range.value.max, 0) + '°')
</script>

<template>
  <div :class="weatherCardClass(w, size)" data-widget="weather"
       @click="store.openWeatherDrawer()">
    <div class="wc-head">
      <span class="wc-glyph" v-html="icon"></span>
      <span class="wc-city">{{ (w && w.city) || '天气' }}</span>
      <span v-if="size !== 'sm' && fields.includes('text')" class="wc-tag">
        {{ w && w.unavailable ? '暂不可用' : '天气' }}
      </span>
      <div class="wc-sizes in-card">
        <button v-for="s in SIZES" :key="s" type="button" class="wc-size"
                :class="{ active: s === size }" :title="SIZE_TITLES[s]"
                @click.stop="store.setWeatherSize(s)">{{ SIZE_LABELS[s] }}</button>
      </div>
    </div>

    <div class="wc-primary">
      <span class="wc-temp">{{ tempText(w && w.temp, 0) }}°</span>
      <span class="wc-text">{{ (w && w.text) || '--' }}</span>
    </div>

    <div v-if="size !== 'sm' && metrics.length" class="wc-metrics">
      <div v-for="m in metrics" :key="m.key" class="wc-metric">
        <span class="wc-metric-k">{{ m.label }}</span>
        <span class="wc-metric-v">{{ m.value }}</span>
      </div>
    </div>

    <div v-if="hasHourly" class="wc-chart">
      <div v-if="!points.length" class="ct-chart-empty">暂无逐时预报数据</div>
      <template v-else>
        <div class="ct-chart-cap">
          <span>{{ chartCap }}</span>
          <span class="ct-chart-last">{{ rangeText }}</span>
        </div>
        <div class="ct-chart-svg">
          <SparklineChart :points="points" :format="tempFormat" time-mode="index"
                          :labels="labels" :w="240" :h="48" color="var(--accent)" />
        </div>
        <div class="ct-chart-cap">
          <span>{{ labels[0] }}</span><span>{{ labels[1] }}</span>
        </div>
      </template>
    </div>

    <div class="wc-foot">
      <span>{{ weatherFoot(w) }}</span>
      <span class="wc-more">详情 ›</span>
    </div>
  </div>
</template>
