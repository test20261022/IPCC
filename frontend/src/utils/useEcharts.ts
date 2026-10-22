import { onBeforeUnmount, onMounted, shallowRef, type Ref } from 'vue'

import echarts, { type EChartsOption } from '@/utils/echarts'

type ChartInstance = ReturnType<typeof echarts.init>

/**
 * 图表生命周期管理：挂载时初始化、窗口缩放自适应、卸载时销毁。
 * 报表与实时监控两页共用，避免各自重复一套 init/resize/dispose。
 */
export function useEcharts(el: Ref<HTMLDivElement | undefined>) {
  const chart = shallowRef<ChartInstance | null>(null)

  /** 更新图表数据（整体替换配置，避免残留上一次的系列） */
  function render(option: EChartsOption): void {
    chart.value?.setOption(option, true)
  }

  function resize(): void {
    chart.value?.resize()
  }

  onMounted(() => {
    if (!el.value) return
    chart.value = echarts.init(el.value)
    window.addEventListener('resize', resize)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('resize', resize)
    chart.value?.dispose()
    chart.value = null
  })

  return { chart, render, resize }
}

/** 秒 → 可读时长（供报表与监控展示通话时长） */
export function formatDuration(seconds: number | null | undefined): string {
  const total = Math.max(0, Math.floor(seconds ?? 0))
  if (total < 60) return `${total} 秒`
  const minutes = Math.floor(total / 60)
  const rest = total % 60
  if (minutes < 60) return rest ? `${minutes} 分 ${rest} 秒` : `${minutes} 分`
  const hours = Math.floor(minutes / 60)
  const restMinutes = minutes % 60
  return restMinutes ? `${hours} 小时 ${restMinutes} 分` : `${hours} 小时`
}
