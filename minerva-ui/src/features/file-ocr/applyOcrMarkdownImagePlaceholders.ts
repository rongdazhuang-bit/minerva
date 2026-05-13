/**
 * Replace OCR engine placeholder substrings in markdown using a ``placeholder -> url`` map.
 *
 * Keys are applied in **descending length** order so shorter keys do not break longer ones.
 */
export function applyOcrMarkdownImagePlaceholders(
  text: string | null | undefined,
  images: Record<string, string> | null | undefined,
): string {
  const base = text ?? ''
  if (images == null || Object.keys(images).length === 0) {
    return base
  }
  const keys = Object.keys(images).sort((a, b) => b.length - a.length)
  let out = base
  for (const k of keys) {
    const val = images[k]
    if (val === undefined) continue
    out = out.split(k).join(val)
  }
  return out
}
