import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import type { PluggableList } from 'unified'
import { MINERVA_MARKDOWN_SANITIZE_SCHEMA } from '@/components/markdown/markdownSanitize'

/** Shared remark plugins (GFM + TeX). */
export const MINERVA_MARKDOWN_REMARK_PLUGINS: PluggableList = [remarkGfm, remarkMath]

/** Shared rehype plugins (raw HTML, KaTeX, sanitize). */
export const MINERVA_MARKDOWN_REHYPE_PLUGINS: PluggableList = [
  rehypeRaw,
  [rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false }],
  [rehypeSanitize, MINERVA_MARKDOWN_SANITIZE_SCHEMA],
]
