import { Skeleton } from 'antd'
import type { CSSProperties } from 'react'

type SiderMenuSkeletonProps = {
  /** Side nav collapsed to icon-only width. */
  collapsed: boolean
  /** Sunshine light shell (adjusts skeleton contrast). */
  light: boolean
  /** Accessible label while nav APIs load. */
  loadingLabel: string
}

/** Row width ratios (0–1) to mimic real menu labels of varying length. */
const EXPANDED_ROW_WIDTHS = [0.62, 0.48, 0.55, 0.42, 0.58, 0.36, 0.5, 0.44]

/** Indent level per row: 0 = top-level, 1 = nested item. */
const EXPANDED_ROW_LEVELS = [0, 0, 0, 1, 1, 0, 0, 0]

const rowStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 10,
  height: 40,
  paddingInline: 16,
}

/** Skeleton placeholder matching inline sider menu row height and spacing. */
export function SiderMenuSkeleton({ collapsed, light, loadingLabel }: SiderMenuSkeletonProps) {
  const skeletonClass = light
    ? 'minerva-app-sider-menu-skeleton minerva-app-sider-menu-skeleton--light'
    : 'minerva-app-sider-menu-skeleton'

  if (collapsed) {
    return (
      <div
        className={skeletonClass}
        aria-busy
        aria-label={loadingLabel}
        style={{ paddingTop: 8 }}
      >
        {EXPANDED_ROW_WIDTHS.slice(0, 6).map((_, index) => (
          <div
            key={index}
            style={{
              ...rowStyle,
              justifyContent: 'center',
              paddingInline: 0,
            }}
          >
            <Skeleton.Avatar active size={18} shape="square" />
          </div>
        ))}
      </div>
    )
  }

  return (
    <div
      className={skeletonClass}
      aria-busy
      aria-label={loadingLabel}
      style={{ paddingTop: 8 }}
    >
      {EXPANDED_ROW_WIDTHS.map((widthRatio, index) => {
        const level = EXPANDED_ROW_LEVELS[index] ?? 0
        return (
          <div
            key={index}
            style={{
              ...rowStyle,
              paddingLeft: 16 + level * 20,
            }}
          >
            <Skeleton.Avatar active size={16} shape="square" />
            <Skeleton.Input
              active
              size="small"
              style={{
                width: `calc((100% - 42px) * ${widthRatio})`,
                minWidth: 48,
                height: 14,
              }}
            />
          </div>
        )
      })}
    </div>
  )
}
