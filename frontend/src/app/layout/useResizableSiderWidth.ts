import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react'

const STORAGE_KEY = 'minerva_sider_width'
const STORAGE_COLLAPSED_KEY = 'minerva_sider_collapsed'
export const SIDER_MIN_PX = 120
export const SIDER_MAX_RATIO = 0.2
/** 折叠后仅显示图标的侧栏宽度（与 Ant Design Sider 默认一致）。 */
export const SIDER_COLLAPSED_PX = 64
const DEFAULT_PX = 200

function readInitialWidth(): number {
  if (typeof window === 'undefined') return DEFAULT_PX
  const raw = localStorage.getItem(STORAGE_KEY)
  const n = parseInt(raw ?? '', 10)
  return Number.isNaN(n) ? DEFAULT_PX : n
}

function readInitialCollapsed(): boolean {
  if (typeof window === 'undefined') return false
  return localStorage.getItem(STORAGE_COLLAPSED_KEY) === '1'
}

/** 左侧导航：可拖曳调宽、可折叠为图标栏；宽度与折叠态持久化到 localStorage。 */
export function useResizableSiderWidth() {
  const rowRef = useRef<HTMLDivElement>(null)
  const [siderWidth, setSiderWidth] = useState(readInitialWidth)
  const [collapsed, setCollapsed] = useState(readInitialCollapsed)
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

  useEffect(() => {
    localStorage.setItem(STORAGE_COLLAPSED_KEY, collapsed ? '1' : '0')
  }, [collapsed])

  const toggleCollapsed = useCallback(() => {
    setCollapsed((c) => !c)
  }, [])

  const beginResizeDrag = useCallback(
    (clientX: number) => {
      drag.current = { active: true, startX: clientX, startW: siderWidth }
      const onMove = (ev: MouseEvent | TouchEvent) => {
        if (!drag.current.active) return
        const x = 'touches' in ev ? ev.touches[0]?.clientX : ev.clientX
        if (x == null) return
        const next = drag.current.startW + (x - drag.current.startX)
        setSiderWidth(clamp(next))
      }
      const onUp = () => {
        drag.current.active = false
        window.removeEventListener('mousemove', onMove)
        window.removeEventListener('mouseup', onUp)
        window.removeEventListener('touchmove', onMove)
        window.removeEventListener('touchend', onUp)
        window.removeEventListener('touchcancel', onUp)
      }
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
      window.addEventListener('touchmove', onMove, { passive: false })
      window.addEventListener('touchend', onUp)
      window.addEventListener('touchcancel', onUp)
    },
    [siderWidth, clamp],
  )

  const onResizeStart = useCallback(
    (e: React.MouseEvent) => {
      if (collapsed) return
      e.preventDefault()
      e.stopPropagation()
      beginResizeDrag(e.clientX)
    },
    [collapsed, beginResizeDrag],
  )

  const onResizeTouchStart = useCallback(
    (e: React.TouchEvent) => {
      if (collapsed) return
      e.preventDefault()
      e.stopPropagation()
      const touch = e.touches[0]
      if (!touch) return
      beginResizeDrag(touch.clientX)
    },
    [collapsed, beginResizeDrag],
  )

  return {
    rowRef,
    siderWidth,
    collapsed,
    toggleCollapsed,
    onResizeStart,
    onResizeTouchStart,
  }
}
