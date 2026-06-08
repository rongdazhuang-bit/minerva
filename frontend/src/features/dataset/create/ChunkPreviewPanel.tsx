/** Dify-style chunk preview panel for the create wizard step 2. */

import { DownOutlined, FileTextOutlined } from '@ant-design/icons'
import { Dropdown, Spin, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import './ChunkPreviewPanel.css'

export type PreviewSegment = {
  content: string
  word_count: number
  answer?: string
  child_count?: number
}

export type PreviewUploadFile = {
  id: string
  name: string
}

export type ChunkPreviewPanelProps = {
  uploads: PreviewUploadFile[]
  previewFileId?: string
  onPreviewFileIdChange: (fileId: string) => void
  segments: PreviewSegment[]
  /** Total segment count from estimate API (may exceed displayed segments). */
  segmentCount: number
  loading?: boolean
  /** Whether user has run preview at least once for the current file. */
  previewReady?: boolean
}

/** Right pane: file picker, chunk count badge, and segment cards. */
export function ChunkPreviewPanel({
  uploads,
  previewFileId,
  onPreviewFileIdChange,
  segments,
  segmentCount,
  loading,
  previewReady,
}: ChunkPreviewPanelProps) {
  const { t } = useTranslation()
  const selectedFile = uploads.find((item) => item.id === previewFileId)
  const selectedFileName = selectedFile?.name ?? t('dataset.create.preview.noFile')
  const displayedCount = previewReady ? segmentCount : 0
  const truncated = previewReady && segmentCount > segments.length

  const fileMenuItems = useMemo<MenuProps['items']>(
    () =>
      uploads.map((item) => ({
        key: item.id,
        label: item.name,
      })),
    [uploads],
  )

  return (
    <div className="minerva-chunk-preview">
      <Typography.Title level={5} className="minerva-chunk-preview__title">
        {t('dataset.create.preview.title')}
      </Typography.Title>

      <div className="minerva-chunk-preview__toolbar">
        <Dropdown
          menu={{
            items: fileMenuItems,
            selectedKeys: previewFileId ? [previewFileId] : [],
            onClick: ({ key }) => onPreviewFileIdChange(String(key)),
          }}
          trigger={['click']}
          disabled={uploads.length === 0}
        >
          <button type="button" className="minerva-chunk-preview__file-trigger">
            <FileTextOutlined className="minerva-chunk-preview__file-icon" />
            <span className="minerva-chunk-preview__file-name">{selectedFileName}</span>
            <DownOutlined className="minerva-chunk-preview__file-chevron" />
          </button>
        </Dropdown>
        <span className="minerva-chunk-preview__chunk-badge">
          {t('dataset.create.preview.estimatedChunks', { count: displayedCount })}
        </span>
      </div>

      <Spin spinning={loading}>
        <div className="minerva-chunk-preview__body minerva-scrollbar-thin">
          {previewReady && segments.length > 0 ? (
            <>
              {truncated ? (
                <Typography.Text type="secondary" className="minerva-chunk-preview__truncated-hint">
                  {t('dataset.create.preview.truncatedHint', { count: segments.length })}
                </Typography.Text>
              ) : null}
              <div className="minerva-chunk-preview__segments">
                {segments.map((seg, idx) => (
                  <div key={idx} className="minerva-chunk-preview__segment">
                    <div className="minerva-chunk-preview__segment-head">
                      <span className="minerva-chunk-preview__segment-index">#{idx + 1}</span>
                      <span className="minerva-chunk-preview__segment-meta">
                        {t('dataset.create.preview.charCount', { count: seg.word_count })}
                      </span>
                    </div>
                    <div className="minerva-chunk-preview__segment-content">{seg.content}</div>
                    {seg.answer ? (
                      <div className="minerva-chunk-preview__segment-extra">
                        {t('dataset.create.previewAnswer')}: {seg.answer}
                      </div>
                    ) : null}
                    {seg.child_count ? (
                      <div className="minerva-chunk-preview__segment-extra">
                        {t('dataset.create.previewChildCount', { count: seg.child_count })}
                      </div>
                    ) : null}
                  </div>
                ))}
              </div>
            </>
          ) : null}
        </div>
      </Spin>
    </div>
  )
}
