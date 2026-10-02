import * as echarts from 'echarts'

const AXIS = {
  axisLine: { lineStyle: { color: 'rgba(56,189,248,0.3)' } },
  axisLabel: { color: '#7d93b2', fontSize: 10 },
  splitLine: { lineStyle: { color: 'rgba(56,189,248,0.08)' } },
}

/** 统一的深色极客风 ECharts 挂载 */
export function mountChart(el, option) {
  const inst = echarts.getInstanceByDom(el) || echarts.init(el)
  inst.setOption(
    {
      color: ['#00e5a0', '#38bdf8', '#a78bfa', '#fbbf24', '#ff5c7a', '#34d399', '#f472b6'],
      backgroundColor: 'transparent',
      textStyle: { color: '#9fb8ce', fontSize: 11 },
      tooltip: { trigger: 'axis', backgroundColor: 'rgba(10,17,30,0.95)', borderColor: 'rgba(0,229,160,0.3)', textStyle: { color: '#c9d6e8', fontSize: 11 } },
      grid: { left: 40, right: 18, top: 30, bottom: 26 },
      ...option,
    },
    true,
  )
  const onResize = () => inst.resize()
  window.addEventListener('resize', onResize)
  return inst
}

export function categoryAxis(data) {
  return { type: 'category', data, ...AXIS }
}
export function valueAxis(name) {
  return { type: 'value', name, ...AXIS }
}
