/** Shared two-pane layout for chunking configuration and segment preview. */

import type { ReactNode } from 'react'
import '@/features/dataset/create/StepTwoChunking.css'

export type ChunkingConfigPreviewLayoutProps = {
  configPane: ReactNode
  previewPane: ReactNode
}

/** Left config form and right preview with independent vertical scroll. */
export function ChunkingConfigPreviewLayout({
  configPane,
  previewPane,
}: ChunkingConfigPreviewLayoutProps) {
  return (
    <div className="minerva-dataset-step-two">
      <div className="minerva-dataset-step-two__pane minerva-dataset-step-two__pane--form minerva-scrollbar-thin">
        {configPane}
      </div>
      <div className="minerva-dataset-step-two__pane minerva-dataset-step-two__pane--preview">
        {previewPane}
      </div>
    </div>
  )
}

/** Visual divider between stacked sections in the config pane. */
export function ChunkingConfigSectionDivider() {
  return <div className="minerva-dataset-step-two__section-divider" role="separator" />
}
