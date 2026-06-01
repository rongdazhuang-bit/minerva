/** Generate ``count`` distinct random HSL colors (readable on dark chat backgrounds). */
export function randomChartColors(count: number): string[] {
  const n = Math.max(0, Math.floor(count))
  if (n === 0) return []

  const colors: string[] = []
  const step = 360 / n
  for (let i = 0; i < n; i++) {
    const hue = (step * i + Math.random() * step * 0.7) % 360
    const sat = 58 + Math.floor(Math.random() * 24)
    const light = 54 + Math.floor(Math.random() * 14)
    colors.push(`hsl(${Math.round(hue)}, ${sat}%, ${light}%)`)
  }
  return colors
}
