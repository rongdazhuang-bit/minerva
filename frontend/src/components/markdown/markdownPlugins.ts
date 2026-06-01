import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import type { PluggableList } from 'unified'
import { MINERVA_MARKDOWN_SANITIZE_SCHEMA } from '@/components/markdown/markdownSanitize'
import { rehypeMathInHtmlTableCells } from '@/components/markdown/rehypeMathInHtmlTableCells'
import { remarkMathInTableCells } from '@/components/markdown/remarkMathInTableCells'

/** Shared remark plugins (GFM + TeX + table-cell math re-parse). */
export const MINERVA_MARKDOWN_REMARK_PLUGINS: PluggableList = [
  remarkGfm,
  remarkMath,
  remarkMathInTableCells,
]

/** Shared rehype plugins (raw HTML, KaTeX, sanitize). */
export const MINERVA_MARKDOWN_REHYPE_PLUGINS: PluggableList = [
  rehypeRaw,
  rehypeMathInHtmlTableCells,
  [rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false }],
  [rehypeSanitize, MINERVA_MARKDOWN_SANITIZE_SCHEMA],
]
