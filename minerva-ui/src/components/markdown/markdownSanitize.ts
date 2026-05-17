import { defaultSchema, type Options } from 'rehype-sanitize'

/**
 * Shared rehype-sanitize schema for Minerva Markdown (GFM tables, KaTeX spans, ``data:image`` on ``img``).
 */
export const MINERVA_MARKDOWN_SANITIZE_SCHEMA: Options = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'caption', 'col', 'colgroup'],
  ancestors: {
    ...defaultSchema.ancestors,
    caption: ['table'],
    col: ['colgroup', 'table'],
    colgroup: ['table'],
  },
  protocols: {
    ...defaultSchema.protocols,
    /** Remote URLs and inlined ``data:image/...`` (OCR / model output). */
    src: ['http', 'https', 'data'],
  },
  attributes: {
    ...defaultSchema.attributes,
    /** KaTeX (``output: 'html'``) uses nested spans with ``className`` and inline ``style``. */
    span: ['className', 'style', 'ariaHidden', 'title'],
  },
}
