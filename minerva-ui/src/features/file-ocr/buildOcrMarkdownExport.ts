/**
 * Builds a single Markdown file body for exporting OCR results (images inlined like the in-app preview).
 */

import type { OcrFileMarkdownPages } from '@/api/ocrTask'
import { normalizeMarkdownForOcr } from '@/components/markdown'

/** User-visible strings for page headings and empty-page placeholder (from i18n at call site). */
export type OcrMarkdownExportLabels = {
  /** H1 title line for the whole document. */
  documentTitle: string
  /** Returns the H2 line for one page (1-based page number). */
  pageTitle: (pageNumber: number) => string
  /** Shown when a page has no markdown after normalization. */
  pageEmpty: string
}

/**
 * Applies the same markdown normalization pipeline as the task detail drawer so math and images match the UI.
 */
function normalizePageMarkdownForExport(
  markdown: string | null | undefined,
  images: Record<string, string> | null | undefined,
): string {
  return normalizeMarkdownForOcr(markdown, images).trimEnd()
}

/**
 * Concatenates all OCR pages into one Markdown document with H1 title, per-page H2, and horizontal rules between pages.
 */
export function buildOcrMarkdownDocumentForExport(
  data: OcrFileMarkdownPages,
  labels: OcrMarkdownExportLabels,
): string {
  const parts: string[] = []
  parts.push(`# ${labels.documentTitle}`)
  parts.push('')
  for (let idx = 0; idx < data.pages.length; idx++) {
    const page = data.pages[idx]
    const n = typeof page.page_index === 'number' ? page.page_index + 1 : idx + 1
    const md = normalizePageMarkdownForExport(page.markdown_text, page.images)
    parts.push(`## ${labels.pageTitle(n)}`)
    parts.push('')
    parts.push(md.trim() === '' ? labels.pageEmpty : md)
    parts.push('')
    if (idx < data.pages.length - 1) {
      parts.push('---')
      parts.push('')
    }
  }
  return parts.join('\n')
}

/**
 * Strips characters unsafe in Windows/macOS filenames and trims length; removes a trailing ``.md`` before sanitizing stem.
 */
export function sanitizeMarkdownDownloadBasename(raw: string): string {
  const trimmed = raw.trim()
  const withoutMd = trimmed.toLowerCase().endsWith('.md') ? trimmed.slice(0, -3) : trimmed
  const s = withoutMd.replace(/[<>:"/\\|?*\u0000-\u001f]/g, '_').replace(/\s+/g, ' ').trim()
  return s.slice(0, 120) || 'ocr-result'
}

/**
 * Triggers a browser download of UTF-8 Markdown with a ``text/markdown`` blob.
 */
export function triggerMarkdownFileDownload(body: string, filename: string): void {
  const blob = new Blob([body], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.rel = 'noopener'
  a.click()
  URL.revokeObjectURL(url)
}
