import { defaultUrlTransform } from 'react-markdown'

/**
 * Keeps ``http``/``https`` (and relative) URLs while allowing ``data:image/...`` for inlined assets.
 */
export function minervaMarkdownUrlTransform(url: string): string {
  const v = url.trim()
  if (v.toLowerCase().startsWith('data:image/')) {
    return v
  }
  return defaultUrlTransform(url)
}
