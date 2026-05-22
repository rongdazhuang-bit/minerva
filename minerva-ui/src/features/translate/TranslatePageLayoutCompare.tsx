/**
 * 翻译任务页面对照：按页展示页图与段落一一对照，避免整页 Markdown 重复堆叠。
 */
import type { CSSProperties } from 'react'
import { Typography } from 'antd'
import { useTranslation } from 'react-i18next'
import { DictText } from '@/components/dict'
import { MinervaMarkdown } from '@/components/markdown'
import type { LayoutPageOut } from '@/api/layoutPages'
import type { DocTranslateSegment, DocTranslateSegmentGroup } from '@/api/translate'
import {
  DOC_TRANSLATE_SEGMENT_DONE,
  DOC_TRANSLATE_SEGMENT_FAILED,
  DOC_TRANSLATE_SEGMENT_PENDING,
  TRANSLATE_SEGMENT_STATUS_DICT_CODE,
} from '@/features/translate/constants'
import '@/components/layout/LayoutPageViewer.css'

const { Text } = Typography

export type TranslatePageLayoutCompareProps = {
  pages: LayoutPageOut[]
  groups: DocTranslateSegmentGroup[]
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

/** 单段原文/译文对照行（页面对照：无边框，直接展示正文）。 */
function PageSegmentPair({ segment }: { segment: DocTranslateSegment }) {
  const { t } = useTranslation()
  return (
    <div className="translate-page__page-pair">
      <div className="translate-page__page-cell translate-page__page-cell--source">
        <MinervaMarkdown preset="ocr" markdown={segment.source_text} />
      </div>
      <div className="translate-page__page-cell translate-page__page-cell--target">
        {segment.translated_text?.trim() ? (
          <MinervaMarkdown preset="ocr" markdown={segment.translated_text} />
        ) : segment.status === DOC_TRANSLATE_SEGMENT_FAILED ? (
          <Text type="danger">
            <DictText dictCode={TRANSLATE_SEGMENT_STATUS_DICT_CODE} value={segment.status} />
          </Text>
        ) : segment.status === DOC_TRANSLATE_SEGMENT_DONE ? (
          <Text type="secondary">{t('translate.segmentMissing')}</Text>
        ) : (
          <Text type="secondary">
            <DictText
              dictCode={TRANSLATE_SEGMENT_STATUS_DICT_CODE}
              value={segment.status || DOC_TRANSLATE_SEGMENT_PENDING}
            />
          </Text>
        )}
      </div>
    </div>
  )
}

/** 按页渲染页图与段落对照；无段落时回退为单页 Markdown 双栏。 */
export function TranslatePageLayoutCompare({ pages, groups }: TranslatePageLayoutCompareProps) {
  const { t } = useTranslation()
  const groupByPage = new Map<number | null, DocTranslateSegmentGroup>()
  for (const g of groups) {
    groupByPage.set(g.page_index ?? null, g)
  }

  const sortedPages = [...pages].sort((a, b) => (a.page_index ?? 0) - (b.page_index ?? 0))

  return (
    <div className="layout-page-viewer">
      {sortedPages.map((page, idx) => {
        const pageIndex = page.page_index ?? idx
        const n = pageIndex + 1
        const group = groupByPage.get(page.page_index ?? null)
        const segments = group?.segments ?? []

        return (
          <section key={`${page.page_index}-${idx}`} className="layout-page-viewer__page">
            <h2 className="layout-page-viewer__title">
              {t('translate.detailPageTitle', { n, defaultValue: `第 ${n} 页` })}
            </h2>
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
                    return (
                      <div key={b.block_key} className="layout-page-viewer__box" style={style} />
                    )
                  })}
                </div>
              </div>
            ) : null}
            {segments.length > 0 ? (
              <div className="translate-page__page-compare">
                <div className="translate-page__page-compare-header">
                  <div className="layout-page-viewer__col-title">{t('translate.colSource')}</div>
                  <div className="layout-page-viewer__col-title">{t('translate.colTarget')}</div>
                </div>
                {segments.map((s) => (
                  <PageSegmentPair key={s.id} segment={s} />
                ))}
              </div>
            ) : (
              <div className="layout-page-viewer__compare">
                <div>
                  <div className="layout-page-viewer__col-title">{t('translate.colSource')}</div>
                  <MinervaMarkdown
                    preset="ocr"
                    markdown={page.source_markdown}
                    images={page.images}
                  />
                </div>
                <div>
                  <div className="layout-page-viewer__col-title">{t('translate.colTarget')}</div>
                  <MinervaMarkdown
                    preset="ocr"
                    markdown={page.translated_markdown ?? ''}
                    images={page.images}
                  />
                </div>
              </div>
            )}
          </section>
        )
      })}
    </div>
  )
}
