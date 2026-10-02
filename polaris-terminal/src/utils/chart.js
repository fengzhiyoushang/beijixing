import * as echarts from 'echarts'

const ACCENT = () => getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#4ade80'

/** 轻微发光效果 */
export function glow(color = undefined, blur = 10) {
  const c = color || ACCENT()
  return { shadowColor: c + '99', shadowBlur: blur }
}

export const axisBase = () => ({
  axisLine: { lineStyle: { color: '#2a2a2a' } },
  axisTick: { show: false },
  axisLabel: { color: '#6b7280', fontSize: 10 },
  splitLine: { lineStyle: { color: 'rgba(42,42,42,0.7)' } },
})

/**
 * 在 DOM 上挂载带辉光主题的 ECharts 实例（重复挂载自动替换）
 */
export function mountChart(el, option) {
  if (!el) return null
  // 复用 DOM 时清理旧的（可能已 dispose 的）实例，避免 "Instance has been disposed" 告警
  const old = echarts.getInstanceByDom(el)
  if (old && !old.isDisposed()) old.dispose()
  el.removeAttribute('_echarts_instance_')
  const chart = echarts.init(el)
  chart.setOption({
    textStyle: { fontFamily: 'PingFang SC, Microsoft YaHei, Segoe UI, sans-serif', color: '#98a29c' },
    animationDuration: 600,
    ...option,
  })
  const ro = new ResizeObserver(() => {
    if (!chart.isDisposed()) chart.resize()
  })
  ro.observe(el)
  chart.__ro = ro
  return chart
}

/** 渐变柱体（辉光） */
export function glowBar(color = undefined) {
  const c = color || ACCENT()
  return {
    type: 'bar',
    itemStyle: {
      borderRadius: [4, 4, 0, 0],
      color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: c },
        { offset: 1, color: c + '33' },
      ]),
      ...glow(c, 12),
    },
  }
}

/** 发光折线 */
export function glowLine(color = undefined) {
  const c = color || ACCENT()
  return {
    type: 'line',
    smooth: true,
    symbol: 'circle',
    symbolSize: 5,
    lineStyle: { width: 2, color: c, ...glow(c, 8) },
    itemStyle: { color: c },
  }
}
