import type { McpTool } from '@/api/mcp'

/** Filter MCP tools by name/description; all whitespace-separated tokens must match. */
export function filterMcpTools(tools: McpTool[], query: string): McpTool[] {
  const tokens = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
  if (tokens.length === 0) return tools
  return tools.filter((tool) => {
    const haystack = `${tool.name}\n${tool.description ?? ''}`.toLowerCase()
    return tokens.every((token) => haystack.includes(token))
  })
}

export type TextHighlightPart = { text: string; match: boolean }

/** Split text into matched / unmatched segments for search highlighting. */
export function splitTextHighlight(text: string, query: string): TextHighlightPart[] {
  const trimmed = query.trim()
  if (!trimmed) return [{ text, match: false }]
  const lowerText = text.toLowerCase()
  const lowerQuery = trimmed.toLowerCase()
  const idx = lowerText.indexOf(lowerQuery)
  if (idx === -1) return [{ text, match: false }]
  const parts: TextHighlightPart[] = []
  if (idx > 0) parts.push({ text: text.slice(0, idx), match: false })
  parts.push({ text: text.slice(idx, idx + trimmed.length), match: true })
  const rest = text.slice(idx + trimmed.length)
  if (rest) parts.push({ text: rest, match: false })
  return parts
}
