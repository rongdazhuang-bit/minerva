/**
 * 智能体对话消息 Markdown（委托 ``MinervaMarkdown`` 公共渲染器）。
 */
import { memo } from 'react'
import { MinervaMarkdown } from '@/components/markdown'
import './AgentAssistantMarkdown.css'

type AgentAssistantMarkdownProps = {
  /** 消息 Markdown 正文（用户/助手；流式过程中可为片段）。 */
  markdown: string
}

export const AgentAssistantMarkdown = memo(function AgentAssistantMarkdown({
  markdown,
}: AgentAssistantMarkdownProps) {
  return <MinervaMarkdown preset="agent" markdown={markdown} />
})
