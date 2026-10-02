<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { store } from '../store'
import { mountChart } from '../utils/chart'

const props = defineProps({
  option: { type: Object, required: true },
  height: { type: String, default: '240px' },
})

const el = ref(null)
let chart = null
let observer = null

/** 首次挂载创建实例；后续仅 setOption（避免反复 dispose 造成的闪烁与告警） */
function render() {
  if (!el.value) return
  if (!chart || chart.isDisposed?.()) {
    chart = mountChart(el.value, props.option)
    const ro = new ResizeObserver(() => chart && !chart.isDisposed?.() && chart.resize())
    ro.observe(el.value)
    observer = ro
  } else {
    chart.setOption(props.option, true)
  }
}

onMounted(render)
onUnmounted(() => {
  observer?.disconnect()
  if (chart && !chart.isDisposed?.()) chart.dispose()
  chart = null
})

// 选项变化（含主题色切换）时更新
watch(() => [props.option, store.settings.accent], render, { deep: true })

const boxStyle = computed(() => ({ width: '100%', height: props.height }))
</script>

<template>
  <div ref="el" :style="boxStyle" class="glow-chart" />
</template>

<style scoped>
.glow-chart { filter: drop-shadow(0 0 6px rgba(74, 222, 128, 0.08)); }
</style>
