/**
 * Shared Markdown renderer: GFM, KaTeX, optional Prism + Mermaid (agent preset).
 */
import { CopyOutlined } from '@ant-design/icons'
import {
  Children,
  isValidElement,
  memo,
  useCallback,
  useEffect,
  useRef,
  type ComponentProps,
  type ReactNode,
} from 'react'
import { useTranslation } from 'react-i18next'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useAppMessage } from '@/app/useAppMessage'
import { copyTextToClipboard } from '@/components/markdown/copyToClipboard'
import {
  MINERVA_MARKDOWN_REHYPE_PLUGINS,
  MINERVA_MARKDOWN_REMARK_PLUGINS,
} from '@/components/markdown/markdownPlugins'
import { minervaMarkdownUrlTransform } from '@/components/markdown/markdownUrlTransform'
import {
  normalizeMarkdownForAgent,
  normalizeMarkdownForOcr,
} from '@/components/markdown/normalizeMarkdownMath'
import { MarkdownChartBlock } from '@/components/markdown/MarkdownChartBlock'
import {
  isChartFenceLanguage,
} from '@/components/markdown/parseMarkdownChartConfig'
import {
  formatCodeBlockLanguageLabel,
  normalizePrismLanguage,
} from '@/components/markdown/prismLanguages'
import {
  buildMermaidInitializeConfig,
  centerMermaidClusterLabelsLive,
  postProcessMermaidSvg,
} from '@/components/markdown/mermaidTheme'
import { normalizeMermaidSourceForRender } from '@/components/markdown/normalizeMarkdownFences'
import { randomId } from '@/lib/randomId'
import 'katex/dist/katex.min.css'
import './MinervaMarkdown.css'

/** Preset selects math preprocessing and rich code-block features. */
export type MinervaMarkdownPreset = 'agent' | 'ocr'

/** 自 ``react-markdown`` 子树提取纯文本（用于 ``language-mermaid`` 代码块）。 */
function textFromReactNode(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return ''
  if (typeof node === 'string' || typeof node === 'number') return String(node)
  if (Array.isArray(node)) return node.map(textFromReactNode).join('')
  if (isValidElement(node)) {
    const p = node.props as { children?: ReactNode }
    return textFromReactNode(p.children)
  }
  return ''
}

let mermaidModulePromise: Promise<typeof import('mermaid').default> | null = null

/** 懒加载 Mermaid；每次渲染前按当前主题重新 ``initialize``。 */
async function loadMermaidApi() {
  if (!mermaidModulePromise) {
    mermaidModulePromise = import('mermaid').then((mod) => mod.default)
  }
  const mermaid = await mermaidModulePromise
  mermaid.initialize(buildMermaidInitializeConfig())
  return mermaid
}

type CodeLikeProps = { className?: string; children?: ReactNode }

/** Prism-highlighted fenced code with language badge, line numbers, and copy. */
const PrismCodeWithCopy = memo(function PrismCodeWithCopy({
  code,
  language,
  rawLanguage,
}: {
  code: string
  language: string
  rawLanguage: string
}) {
  const { t } = useTranslation()
  const message = useAppMessage()
  const onCopy = useCallback(async () => {
    const ok = await copyTextToClipboard(code)
    if (ok) void message.success(t('agents.copySuccess'))
    else void message.error(t('agents.copyFailed'))
  }, [code, t, message])

  const copyLabel = t('agents.copyCodeBlock')
  const languageLabel = formatCodeBlockLanguageLabel(
    rawLanguage,
    language,
    t('agents.codeLangPlainText'),
  )

  return (
    <div className="minerva-md-syntax-host">
      <div className="minerva-md-syntax-header">
        <span className="minerva-md-syntax-lang" title={languageLabel}>
          {languageLabel}
        </span>
        <button
          type="button"
          className="minerva-md-syntax-copy"
          aria-label={copyLabel}
          title={copyLabel}
          onClick={() => void onCopy()}
        >
          <CopyOutlined />
        </button>
      </div>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        PreTag="div"
        className="minerva-md-syntax"
        codeTagProps={{ className: 'minerva-md-syntax-code' }}
        customStyle={{
          margin: 0,
          padding: '0.75em 0.85em',
          borderRadius: 0,
          fontSize: '0.88em',
          border: 'none',
          background: 'transparent',
          maxHeight: 'none',
          overflowX: 'auto',
          overflowY: 'clip',
        }}
        showLineNumbers
        lineNumberStyle={{
          minWidth: '2.25em',
          paddingRight: '0.75em',
          marginRight: '0.5em',
          textAlign: 'right',
          userSelect: 'none',
          opacity: 0.45,
        }}
        wrapLines
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
})

/** Mount Mermaid SVG via XML parser (avoids ``innerHTML`` breaking ``foreignObject`` markup). */
function mountMermaidSvg(host: HTMLDivElement, rawSvg: string): void {
  const svg = postProcessMermaidSvg(rawSvg)
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  const err = doc.querySelector('parsererror')
  if (err) {
    throw new Error(err.textContent ?? 'mermaid svg parse failed')
  }
  host.replaceChildren()
  host.append(doc.documentElement)
}

/** 将 `` ```mermaid `` 代码块渲染为 SVG（失败时回退为源码文本）。 */
function MermaidBlock({ code }: { code: string }) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    let cancelled = false
    const renderId = `minerva-mmd-${randomId()}`
    const source = normalizeMermaidSourceForRender(code)
    void (async () => {
      try {
        const mermaid = await loadMermaidApi()
        if (cancelled || !hostRef.current) return
        const { svg, bindFunctions } = await mermaid.render(renderId, source)
        if (cancelled || !hostRef.current) return
        mountMermaidSvg(hostRef.current, svg)
        bindFunctions?.(hostRef.current)
        requestAnimationFrame(() => {
          if (!cancelled && hostRef.current) {
            centerMermaidClusterLabelsLive(hostRef.current)
          }
        })
      } catch {
        if (!cancelled && hostRef.current) {
          hostRef.current.replaceChildren()
          const pre = document.createElement('pre')
          pre.className = 'minerva-md-pre minerva-md-mermaid-fallback'
          pre.textContent = code
          hostRef.current.append(pre)
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [code])

  return (
    <div
      ref={hostRef}
      className="minerva-md-mermaid"
      role="img"
      aria-label="Mermaid diagram"
    />
  )
}

/** Agent preset: Mermaid + Prism; OCR preset: plain fenced ``pre``. */
function createPreBlock(richCode: boolean) {
  return function PreBlock(props: ComponentProps<'pre'>) {
    const { children, className, ...rest } = props
    const arr = Children.toArray(children)
    if (richCode && arr.length === 1) {
      const first = arr[0]
      if (isValidElement(first) && typeof first.type === 'string' && first.type === 'code') {
        const cp = first.props as CodeLikeProps
        const cls = String(cp.className ?? '')
        const inner = textFromReactNode(cp.children).replace(/\n$/, '')
        if (cls.includes('language-mermaid')) {
          return <MermaidBlock code={inner} />
        }
        const langMatch = /language-([\w#+.-]+)/i.exec(cls)
        const rawLang = langMatch?.[1] ?? ''
        if (rawLang && isChartFenceLanguage(rawLang)) {
          return <MarkdownChartBlock code={inner} />
        }
        const lang = rawLang ? normalizePrismLanguage(rawLang) : 'plaintext'
        return <PrismCodeWithCopy code={inner} language={lang} rawLanguage={rawLang} />
      }
    }
    return (
      <pre {...rest} className={[className, 'minerva-md-pre'].filter(Boolean).join(' ')}>
        {children}
      </pre>
    )
  }
}

const AGENT_PRE_BLOCK = createPreBlock(true)
const OCR_PRE_BLOCK = createPreBlock(false)

/** Agent chat: wrap wide GFM tables for horizontal scroll without trapping vertical wheel. */
function AgentTableBlock(props: ComponentProps<'table'>) {
  const { children, ...rest } = props
  return (
    <div className="minerva-md-table-scroll">
      <table {...rest}>{children}</table>
    </div>
  )
}

export type MinervaMarkdownProps = {
  /** Raw Markdown source. */
  markdown: string
  /** ``agent``: chat math + Prism/Mermaid; ``ocr``: OCR placeholders + display math fences. */
  preset: MinervaMarkdownPreset
  /** OCR only: placeholder → URL map for inlined images. */
  images?: Record<string, string> | null
  /** Shown when ``markdown`` is empty/whitespace (OCR page empty hint). */
  emptyFallback?: ReactNode
}

export const MinervaMarkdown = memo(function MinervaMarkdown({
  markdown,
  preset,
  images,
  emptyFallback,
}: MinervaMarkdownProps) {
  const trimmed = markdown.trim()
  if (!trimmed) {
    if (emptyFallback != null) {
      return <>{emptyFallback}</>
    }
    return <span className="minerva-md-empty">{'\u00a0'}</span>
  }

  const rendered =
    preset === 'agent'
      ? normalizeMarkdownForAgent(trimmed)
      : normalizeMarkdownForOcr(trimmed, images)

  return (
    <div
      className={preset === 'agent' ? 'minerva-md-wrap minerva-md-wrap--agent' : 'minerva-md-wrap'}
    >
      <div className="minerva-md">
        <ReactMarkdown
          urlTransform={minervaMarkdownUrlTransform}
          remarkPlugins={MINERVA_MARKDOWN_REMARK_PLUGINS}
          rehypePlugins={MINERVA_MARKDOWN_REHYPE_PLUGINS}
          components={
            preset === 'agent'
              ? { pre: AGENT_PRE_BLOCK, table: AgentTableBlock }
              : { pre: OCR_PRE_BLOCK }
          }
        >
          {rendered}
        </ReactMarkdown>
      </div>
    </div>
  )
})
