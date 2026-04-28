import { useEffect, useRef, useState } from 'react'

const easeOutCubic = (t: number) => 1 - (1 - t) ** 3

export type UseCountUpOptions = {
  /** 动画时长（毫秒），默认 900 */
  duration?: number
  /** 为 false 时固定为 0（不播放） */
  enabled?: boolean
}

/**
 * 数值从当前显示值渐变为 end（ease-out），用于仪表盘等数字滚动效果。
 * 依赖变化或 end 变化时会从当前已显示值起播，避免新依赖时从 0 “跳回”。
 */
export function useCountUp(end: number, options?: UseCountUpOptions): number {
  const duration = options?.duration ?? 900
  const enabled = options?.enabled ?? true
  const [value, setValue] = useState(0)
  const valueRef = useRef(0)
  const frameRef = useRef(0)

  useEffect(() => {
    if (!enabled) {
      valueRef.current = 0
      setValue(0)
      return
    }

    if (
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    ) {
      valueRef.current = end
      setValue(end)
      return
    }

    const from = valueRef.current
    let startTs: number | null = null

    const step = (now: number) => {
      if (startTs === null) startTs = now
      const p = Math.min(1, (now - startTs) / duration)
      const next = Math.round(from + (end - from) * easeOutCubic(p))
      valueRef.current = next
      setValue(next)
      if (p < 1) {
        frameRef.current = requestAnimationFrame(step)
      } else {
        valueRef.current = end
        setValue(end)
      }
    }

    frameRef.current = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frameRef.current)
  }, [end, enabled, duration])

  return value
}
