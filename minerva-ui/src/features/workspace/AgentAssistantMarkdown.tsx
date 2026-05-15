/**
 * 对话消息 Markdown：GFM、围栏代码（Prism 多语言高亮 + 角标复制）、TeX（KaTeX）、Mermaid、受限 HTML。
 */
import { CopyOutlined } from '@ant-design/icons'
import { message as antdMessage } from 'antd'
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
import ReactMarkdown, { defaultUrlTransform } from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import rehypeKatex from 'rehype-katex'
import rehypeRaw from 'rehype-raw'
import rehypeSanitize from 'rehype-sanitize'
import remarkGfm from 'remark-gfm'
import remarkMath from 'remark-math'
import { AGENT_CHAT_MARKDOWN_SANITIZE_SCHEMA } from '@/features/workspace/agentChatMarkdownSanitize'
import { normalizePrismLanguage } from '@/features/workspace/agentChatPrismLanguages'
import 'katex/dist/katex.min.css'
import './AgentAssistantMarkdown.css'

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

/**
 * 保留 ``data:image/...`` 于 ``img`` src；其余走 ``defaultUrlTransform``。
 */
function agentChatUrlTransform(url: string): string {
  const v = url.trim()
  if (v.toLowerCase().startsWith('data:image/')) return v
  return defaultUrlTransform(url)
}

let mermaidApiPromise: Promise<typeof import('mermaid').default> | null = null

/** 懒加载 Mermaid 并仅初始化一次（多图块共用）。 */
function loadMermaidApi() {
  if (!mermaidApiPromise) {
    mermaidApiPromise = import('mermaid').then((mod) => {
      const mermaid = mod.default
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: 'dark',
        fontFamily: 'ui-sans-serif, system-ui, sans-serif',
      })
      return mermaid
    })
  }
  return mermaidApiPromise
}

type CodeLikeProps = { className?: string; children?: ReactNode }

/**
 * Copies ``text`` to the system clipboard; falls back to ``document.execCommand('copy')``
 * when ``navigator.clipboard`` is missing or rejects (e.g. non-HTTPS).
 */
async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    /* fall through */
  }
  try {
    const ta = document.createElement('textarea')
    ta.value = text
    ta.setAttribute('readonly', '')
    ta.style.position = 'fixed'
    ta.style.left = '-9999px'
    document.body.appendChild(ta)
    ta.select()
    const ok = document.execCommand('copy')
    document.body.removeChild(ta)
    return ok
  } catch {
    return false
  }
}

/** Prism-highlighted fenced code with copy actions at the top-right and bottom-right. */
const PrismCodeWithCopy = memo(function PrismCodeWithCopy({
  code,
  language,
}: {
  code: string
  language: string
}) {
  const { t } = useTranslation()
  const onCopy = useCallback(async () => {
    const ok = await copyTextToClipboard(code)
    if (ok) void antdMessage.success(t('agents.copySuccess'))
    else void antdMessage.error(t('agents.copyFailed'))
  }, [code, t])

  const copyLabel = t('agents.copyCodeBlock')

  return (
    <div className="agents-page__md-syntax-host">
      <button
        type="button"
        className="agents-page__md-syntax-copy agents-page__md-syntax-copy--tr"
        aria-label={copyLabel}
        title={copyLabel}
        onClick={() => void onCopy()}
      >
        <CopyOutlined />
      </button>
      <button
        type="button"
        className="agents-page__md-syntax-copy agents-page__md-syntax-copy--br"
        aria-label={copyLabel}
        title={copyLabel}
        onClick={() => void onCopy()}
      >
        <CopyOutlined />
      </button>
      <SyntaxHighlighter
        language={language}
        style={oneDark}
        PreTag="div"
        className="agents-page__md-syntax"
        codeTagProps={{ className: 'agents-page__md-syntax-code' }}
        customStyle={{
          margin: 0,
          /* Leave space so long lines and first/last lines stay clear of the corner copy controls. */
          padding: '2rem 2.5rem 2rem 1em',
          borderRadius: 8,
          fontSize: '0.88em',
          border: '1px solid var(--minerva-border, #2a3f58)',
        }}
        showLineNumbers={false}
        wrapLines
        wrapLongLines
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
})

/** 将 `` ```mermaid `` 代码块渲染为 SVG（失败时回退为源码文本）。 */
function MermaidBlock({ code }: { code: string }) {
  const hostRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = hostRef.current
    if (!el) return
    let cancelled = false
    const renderId = `minerva-mmd-${crypto.randomUUID()}`
    void (async () => {
      try {
        const mermaid = await loadMermaidApi()
        if (cancelled || !hostRef.current) return
        const { svg, bindFunctions } = await mermaid.render(renderId, code)
        if (cancelled || !hostRef.current) return
        hostRef.current.innerHTML = svg
        bindFunctions?.(hostRef.current)
      } catch {
        if (!cancelled && hostRef.current) {
          hostRef.current.textContent = code
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
      className="agents-page__md-mermaid"
      role="img"
      aria-label="Mermaid diagram"
    />
  )
}

/** 围栏代码：Mermaid 单独渲染；其余语言走 Prism 高亮；无语言标签时按纯文本块展示。 */
function PreBlock(props: ComponentProps<'pre'>) {
  const { children, className, ...rest } = props
  const arr = Children.toArray(children)
  if (arr.length === 1) {
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
      const lang = rawLang ? normalizePrismLanguage(rawLang) : 'plaintext'
      return <PrismCodeWithCopy code={inner} language={lang} />
    }
  }
  return (
    <pre {...rest} className={[className, 'agents-page__md-pre'].filter(Boolean).join(' ')}>
      {children}
    </pre>
  )
}

type AgentAssistantMarkdownProps = {
  /** 消息 Markdown 正文（用户/助手；流式过程中可为片段）。 */
  markdown: string
}

export const AgentAssistantMarkdown = memo(function AgentAssistantMarkdown({
  markdown,
}: AgentAssistantMarkdownProps) {
  const trimmed = markdown.trim()
  if (!trimmed) {
    return <span className="agents-page__md-empty">{'\u00a0'}</span>
  }

  return (
    <div className="agents-page__md-wrap">
      <div className="agents-page__md">
        <ReactMarkdown
          urlTransform={agentChatUrlTransform}
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[
            rehypeRaw,
            [rehypeKatex, { output: 'html', strict: 'ignore', throwOnError: false }],
            [rehypeSanitize, AGENT_CHAT_MARKDOWN_SANITIZE_SCHEMA],
          ]}
          components={{ pre: PreBlock }}
        >
          {markdown}
        </ReactMarkdown>
      </div>
    </div>
  )
})
