/** Filter and display helpers for MCP resource list search in the explorer panel. */

import type { McpResource } from '@/api/mcp'
import { splitTextHighlight, type TextHighlightPart } from './mcpToolListUtils'

export { splitTextHighlight, type TextHighlightPart }

/** Filter MCP resources by name/uri/description; all whitespace-separated tokens must match. */
export function filterMcpResources(resources: McpResource[], query: string): McpResource[] {
  const tokens = query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
  if (tokens.length === 0) return resources
  return resources.filter((resource) => {
    const haystack = `${resource.name ?? ''}\n${resource.uri}\n${resource.description ?? ''}`.toLowerCase()
    return tokens.every((token) => haystack.includes(token))
  })
}

/** Display title for one resource row. */
export function resourceDisplayName(resource: McpResource): string {
  return resource.name?.trim() || resource.uri
}
