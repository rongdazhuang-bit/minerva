import { describe, expect, it } from 'vitest'

import { applyOcrMarkdownImagePlaceholders } from './applyOcrMarkdownImagePlaceholders'

describe('applyOcrMarkdownImagePlaceholders', () => {
  it('returns empty string for null text and no images', () => {
    expect(applyOcrMarkdownImagePlaceholders(null, null)).toBe('')
  })

  it('applies longer keys before shorter keys', () => {
    const text = 'ab X ac'
    const images = { a: '1', ab: '2' }
    expect(applyOcrMarkdownImagePlaceholders(text, images)).toBe('2 X 1c')
  })

  it('leaves text unchanged when images map is empty', () => {
    expect(applyOcrMarkdownImagePlaceholders('hello', {})).toBe('hello')
  })
})
