import { renderToStaticMarkup } from 'react-dom/server'
import { createElement } from 'react'
import { describe, expect, it } from 'vitest'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import { sanitizeMermaidSvgForXml } from '@/components/markdown/mermaidTheme'
import {
  normalizeMermaidHtmlLineBreaks,
  prepareMarkdownFencedDiagrams,
  repairMermaidFencedBlocks,
  splitInlineOpeningCodeFences,
} from '@/components/markdown/normalizeMarkdownFences'
import { normalizeMarkdownForAgent } from '@/components/markdown/normalizeMarkdownMath'

const SPRING_BOOT_MERMAID = `flowchart TB
    subgraph Client
        A["客户端 (移动/Web)"]
    end

    subgraph "接入层"
        B["负载均衡/Nginx"]
    end

    subgraph "Spring Boot 应用"
        direction TB
        C["Controller 层<br/>(REST API)"]
        DTO)"]
        D["Service 层<br/>(业务逻辑)"]
        E["Repository 层<br/>(数据访问)"]
    end

    subgraph "数据与中间件"
        F["关系型数据库<br/>(MySQL/PostgreSQL)"]
        G["缓存<br/>(Redis)"]
        H["消息队列<br/>(RabbitMQ/Kafka)"]
    end

    A -->|HTTP/HTTPS| B
    B --> C
    C --> D
    D --> E
    D --> G
    D --> H
    E --> F
    E --> G`

function renderFenceLanguage(markdown: string): string | null {
  const html = renderToStaticMarkup(
    createElement(ReactMarkdown, { remarkPlugins: [remarkGfm] }, markdown),
  )
  const match = /class="language-([\w-]+)"/.exec(html)
  return match?.[1] ?? null
}

describe('normalizeMarkdownFences', () => {
  it('splits an opening fence from prose on the same line', () => {
    const input = '图表渲染：```mermaid\nflowchart TB\n```'
    expect(splitInlineOpeningCodeFences(input)).toBe(
      '图表渲染：\n\n```mermaid\nflowchart TB\n```',
    )
  })

  it('removes orphan Mermaid node tails inside mermaid fences', () => {
    const input = '```mermaid\nflowchart TB\nDTO)"]\nA --> B\n```'
    expect(repairMermaidFencedBlocks(input)).toBe('```mermaid\nflowchart TB\nA --> B\n```')
  })

  it('lets remark-gfm recognize inline-prefixed mermaid fences after agent normalize', () => {
    const input = `md渲染兼容如下 图表渲染：\`\`\`mermaid\n${SPRING_BOOT_MERMAID}\n\`\`\``
    const normalized = normalizeMarkdownForAgent(input)
    expect(renderFenceLanguage(normalized)).toBe('mermaid')
    expect(normalized).not.toMatch(/DTO\)"\]/)
  })

  it('prepares the Spring Boot sample without the corrupted node line', () => {
    const input = `\`\`\`mermaid\n${SPRING_BOOT_MERMAID}\n\`\`\``
    const prepared = prepareMarkdownFencedDiagrams(input)
    expect(prepared).not.toMatch(/DTO\)"\]/)
    expect(prepared).not.toMatch(/<br\s*\/?>/i)
    expect(prepared).toContain('Controller 层\n(REST API)')
  })

  it('converts HTML line breaks in mermaid labels to newlines', () => {
    expect(normalizeMermaidHtmlLineBreaks('A["x<br/>y<br>z"]')).toBe('A["x\ny\nz"]')
  })

  it('self-closes bare br tags in mermaid SVG for XML parsers', () => {
    const fixed = sanitizeMermaidSvgForXml(
      '<svg><foreignObject><p>层<br>(REST)</p></foreignObject></svg>',
    )
    expect(fixed).not.toMatch(/<br>(?!\s*<\/)/)
    expect(fixed).toContain('<br/>')
  })
})
