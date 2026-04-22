import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'minerva_sider_width'
export const SIDER_MIN_PX = 120
export const SIDER_MAX_RATIO = 0.2
const DEFAULT_PX = 200

function readInitialWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_PX
  const raw = localStorage.getItem(STORAGE_KEY)
  const n = parseInt(raw ?? '', 10)
  return Number.isNaN(n) ? DEFAULT_PX : n
}

export function useResizableSiderWidth() {
  const rowRef = useRef<HTMLDivElement>(null)
  const [siderWidth, setSiderWidth] = useState(readInitialWidth)
  const drag = useRef({ active: false, startX: 0, startW: 0 })

  const getBounds = useCallback(() => {
    const total = rowRef.current?.clientWidth ?? 0
    if (total <= 0) {
      return { min: SIDER_MIN_PX, max: Math.max(SIDER_MIN_PX, Math.floor(1920 * SIDER_MAX_RATIO)) }
    }
    const max = Math.max(SIDER_MIN_PX, Math.floor(total * SIDER_MAX_RATIO))
    return { min: SIDER_MIN_PX, max }
  }, [])

  const clamp = useCallback(
    (w: number) => {
      const { min, max } = getBounds()
      return Math.min(max, Math.max(min, Math.round(w)))
    },
    [getBounds],
  )

  useLayoutEffect(() => {
    setSiderWidth((w) => clamp(w))
  }, [clamp])

  useEffect(() => {
    const el = rowRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      setSiderWidth((w) => clamp(w))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [clamp])

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, String(siderWidth))
  }, [siderWidth])

  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault()
      e.stopPropagation()
      drag.current = { active: true, startX: e.clientX, startW: siderWidth }
      const onMove = (ev: MouseEvent) => {
        if (!drag.current.active) return
        const next = drag.current.startW + (ev.clientX - drag.current.startX)
        setSiderWidth(clamp(next))
      }
      const onUp = () => {
        drag.current.active = false
        window.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
      }
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    },
    [siderWidth, clamp],
  )

  return { rowRef, siderWidth, onResizeStart }
}
