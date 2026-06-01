import type { CSSProperties } from 'react'
import { MinervaMarkdown } from '@/components/markdown'
import type { LayoutPageOut } from '@/api/layoutPages'
import './LayoutPageViewer.css'

export type LayoutPageViewerMode = 'source' | 'bilingual'

export type LayoutPageViewerProps = {
  pages: LayoutPageOut[]
  mode: LayoutPageViewerMode
  pageTitle: (pageNumber: number) => string
  colSourceTitle?: string
  colTargetTitle?: string
}

function blockStyle(
  bbox: number[] | null,
  width: number | null,
  height: number | null,
): CSSProperties | undefined {
  if (!bbox || bbox.length < 4 || !width || !height) {
    return undefined
  }
  const [x0, y0, x1, y1] = bbox
  return {
    left: `${(x0 / width) * 100}%`,
    top: `${(y0 / height) * 100}%`,
    width: `${((x1 - x0) / width) * 100}%`,
    height: `${((y1 - y0) / height) * 100}%`,
  }
}

/** Page raster + bbox overlay and Markdown comparison columns. */
export function LayoutPageViewer({
  pages,
  mode,
  pageTitle,
  colSourceTitle = '原文',
  colTargetTitle = '译文',
}: LayoutPageViewerProps) {
  return (
    <div className="layout-page-viewer">
      {pages.map((page, idx) => {
        const n = typeof page.page_index === 'number' ? page.page_index + 1 : idx + 1
        return (
          <section key={`${page.page_index}-${idx}`} className="layout-page-viewer__page">
            <h2 className="layout-page-viewer__title">{pageTitle(n)}</h2>
            {page.page_raster_url ? (
              <div className="layout-page-viewer__visual">
                <img
                  className="layout-page-viewer__raster"
                  src={page.page_raster_url}
                  alt=""
                />
                <div className="layout-page-viewer__overlay">
                  {page.blocks.map((b) => {
                    const style = blockStyle(b.bbox, page.width, page.height)
                    if (!style) return null
                    return <div key={b.block_key} className="layout-page-viewer__box" style={style} />
                  })}
                </div>
              </div>
            ) : null}
            {mode === 'bilingual' ? (
              <div className="layout-page-viewer__compare">
                <div>
                  <div className="layout-page-viewer__col-title">{colSourceTitle}</div>
                  <MinervaMarkdown
                    preset="ocr"
                    markdown={page.source_markdown}
                    images={page.images}
                  />
                </div>
                <div>
                  <div className="layout-page-viewer__col-title">{colTargetTitle}</div>
                  <MinervaMarkdown
                    preset="ocr"
                    markdown={page.translated_markdown ?? ''}
                    images={page.images}
                  />
                </div>
              </div>
            ) : (
              <MinervaMarkdown
                preset="ocr"
                markdown={page.source_markdown}
                images={page.images}
              />
            )}
          </section>
        )
      })}
    </div>
  )
}
