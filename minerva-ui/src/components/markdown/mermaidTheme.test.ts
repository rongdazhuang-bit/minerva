import { describe, expect, it } from 'vitest'

import { parseTranslate } from '@/components/markdown/mermaidTheme'

describe('mermaidTheme helpers', () => {
  it('parseTranslate reads translate(tx, ty)', () => {
    expect(parseTranslate('translate(12, 34)')).toEqual({ x: 12, y: 34 })
    expect(parseTranslate('translate(12 34)')).toEqual({ x: 12, y: 34 })
    expect(parseTranslate(null)).toEqual({ x: 0, y: 0 })
  })
})
