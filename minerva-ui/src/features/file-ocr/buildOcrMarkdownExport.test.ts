import { describe, expect, it } from 'vitest'
import type { OcrFileMarkdownPages } from '@/api/ocrTask'
import { buildOcrMarkdownDocumentForExport, sanitizeMarkdownDownloadBasename } from './buildOcrMarkdownExport'

const labels = {
  documentTitle: 'Doc',
  pageTitle: (n: number) => `P${n}`,
  pageEmpty: '(empty)',
}

describe('sanitizeMarkdownDownloadBasename', () => {
  it('strips illegal filename characters', () => {
    expect(sanitizeMarkdownDownloadBasename('a:b*c?.pdf')).toBe('a_b_c_.pdf')
  })

  it('drops trailing .md case-insensitively before sanitize', () => {
    expect(sanitizeMarkdownDownloadBasename('readme.MD')).toBe('readme')
  })
})

describe('buildOcrMarkdownDocumentForExport', () => {
  it('inlines image placeholders and adds page structure', () => {
    const data: OcrFileMarkdownPages = {
      file_id: 'x',
      ocr_type: 'PADDLE_OCR',
      pages: [
        {
          page_index: 0,
          markdown_text: 'Hi ![](__IMG0__)',
          images: { __IMG0__: 'data:image/png;base64,QQ==' },
        },
      ],
    }
    const out = buildOcrMarkdownDocumentForExport(data, labels)
    expect(out).toContain('# Doc')
    expect(out).toContain('## P1')
    expect(out).toContain('![](data:image/png;base64,QQ==)')
  })

  it('uses pageEmpty when markdown is blank', () => {
    const data: OcrFileMarkdownPages = {
      file_id: 'x',
      ocr_type: 'PADDLE_OCR',
      pages: [{ page_index: 1, markdown_text: '   ', images: null }],
    }
    expect(buildOcrMarkdownDocumentForExport(data, labels)).toContain('(empty)')
  })
})
