import { randomChartColors } from '@/components/markdown/chartRandomColors'

/** Build Mermaid ``initialize`` config from Minerva CSS theme variables (transparent plot background). */

/** Read a CSS custom property from ``document.documentElement``. */
function readMinervaCssVar(name: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return value || fallback
}

/** Theme variables: transparent canvas; ink/border from app theme for axes and labels. */
export function buildMermaidInitializeConfig(): import('mermaid').MermaidConfig {
  const border = readMinervaCssVar('--minerva-border', '#2a3f58')
  const ink = readMinervaCssVar('--minerva-ink', '#e8f0f8')
  const [c1, c2, c3, c4] = randomChartColors(4)

  return {
    startOnLoad: false,
    securityLevel: 'strict',
    theme: 'base',
    fontFamily: 'ui-sans-serif, system-ui, sans-serif',
    flowchart: {
      /** SVG ``text`` labels center reliably; HTML ``foreignObject`` titles often measure wrong width. */
      htmlLabels: false,
    },
    themeVariables: {
      background: 'transparent',
      mainBkg: 'transparent',
      secondBkg: 'transparent',
      primaryColor: 'transparent',
      secondaryColor: 'transparent',
      tertiaryColor: 'transparent',
      primaryBorderColor: border,
      secondaryBorderColor: border,
      lineColor: border,
      textColor: ink,
      primaryTextColor: ink,
      secondaryTextColor: ink,
      titleColor: ink,
      labelTextColor: ink,
      actorTextColor: ink,
      signalTextColor: ink,
      noteTextColor: ink,
      taskTextColor: ink,
      gridColor: border,
      sectionBkgColor: 'transparent',
      altSectionBkgColor: 'transparent',
      pie1: c1,
      pie2: c2,
      pie3: c3,
      pie4: c4,
      cScale0: c1,
      cScale1: c2,
      cScale2: c3,
      cScale3: c4,
    },
  }
}

/**
 * Self-close ``<br>`` tags in Mermaid SVG so XML parsers accept foreignObject HTML.
 */
export function sanitizeMermaidSvgForXml(svg: string): string {
  return svg.replace(/<br([^>]*?)>/gi, (_match, attrs: string) => {
    if (attrs.trimEnd().endsWith('/')) return `<br${attrs}>`
    return `<br${attrs}/>`
  })
}

/** Parse ``translate(tx, ty)`` from an SVG ``transform`` attribute. */
export function parseTranslate(transform: string | null): { x: number; y: number } {
  if (!transform) return { x: 0, y: 0 }
  const match = /translate\(\s*([-\d.]+)(?:[,\s]+([-\d.]+))?\s*\)/.exec(transform)
  if (!match) return { x: 0, y: 0 }
  return { x: parseFloat(match[1]), y: parseFloat(match[2] ?? '0') }
}

/** Shift a cluster label ``translate`` by ``dx``/``dy`` in SVG user units. */
function shiftClusterLabelTransform(label: SVGGElement, dx: number, dy = 0): void {
  const { x, y } = parseTranslate(label.getAttribute('transform'))
  label.setAttribute('transform', `translate(${x + dx}, ${y + dy})`)
}

/**
 * After the SVG is in the DOM, nudge subgraph titles to the horizontal center of the cluster ``rect``.
 */
export function centerMermaidClusterLabelsLive(host: HTMLElement): void {
  const svg = host.querySelector('svg')
  if (!svg) return

  const inverse = svg.getScreenCTM()?.inverse()
  if (!inverse) return

  const toSvgX = (clientX: number, clientY: number) => {
    const pt = svg.createSVGPoint()
    pt.x = clientX
    pt.y = clientY
    return pt.matrixTransform(inverse).x
  }

  for (const cluster of svg.querySelectorAll('g.cluster')) {
    const label = cluster.querySelector('g.cluster-label')
    const rect = cluster.querySelector('rect')
    if (!(label instanceof SVGGElement) || !rect) continue

    const cr = rect.getBoundingClientRect()
    const lr = label.getBoundingClientRect()
    if (cr.width <= 0 || lr.width <= 0) continue

    const clusterCenterX = toSvgX(cr.left + cr.width / 2, cr.top)
    const labelCenterX = toSvgX(lr.left + lr.width / 2, lr.top)
    const dx = clusterCenterX - labelCenterX
    if (Number.isFinite(dx) && Math.abs(dx) >= 0.5) {
      shiftClusterLabelTransform(label, dx)
    }
  }
}

/** Post-process Mermaid SVG for theme tweaks (sanitize → background → stroke colors). */
export function postProcessMermaidSvg(svg: string): string {
  const safe = sanitizeMermaidSvgForXml(svg)
  return randomizeMermaidLineColors(harmonizeMermaidSvgBackground(safe))
}

/** Assign random stroke colors to chart-like ``path``/``line`` elements in Mermaid SVG. */
export function randomizeMermaidLineColors(svg: string): string {
  if (typeof DOMParser === 'undefined') return svg

  const palette = randomChartColors(8)
  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  let idx = 0

  for (const el of doc.querySelectorAll('path[stroke], line[stroke]')) {
    const stroke = el.getAttribute('stroke')
    if (!stroke || stroke === 'none' || stroke === 'transparent') continue
    const sw = parseFloat(el.getAttribute('stroke-width') || '1')
    if (sw < 1.25) continue
    el.setAttribute('stroke', palette[idx % palette.length] ?? palette[0])
    idx += 1
  }

  return new XMLSerializer().serializeToString(doc)
}

/** Strip full-canvas background fills from Mermaid SVG so the chat background shows through. */
export function harmonizeMermaidSvgBackground(svg: string): string {
  if (typeof DOMParser === 'undefined') return svg

  const doc = new DOMParser().parseFromString(svg, 'image/svg+xml')
  const root = doc.documentElement
  const svgW = parseFloat(root.getAttribute('width') || '0')
  const svgH = parseFloat(root.getAttribute('height') || '0')

  root.style.background = 'transparent'

  for (const rect of root.querySelectorAll('rect')) {
    const w = parseFloat(rect.getAttribute('width') || '0')
    const h = parseFloat(rect.getAttribute('height') || '0')
    if (svgW > 0 && svgH > 0 && w >= svgW * 0.85 && h >= svgH * 0.85) {
      rect.setAttribute('fill', 'transparent')
    }
  }

  let out = new XMLSerializer().serializeToString(doc)
  const opaqueFills = [
    '#1f2020',
    '#2d2d2d',
    '#333333',
    '#333',
    '#1a1a1a',
    '#222222',
    '#000000',
    '#1a2836',
    '#121c28',
    '#ffffff',
    '#fff',
  ]
  for (const hex of opaqueFills) {
    out = out.replace(new RegExp(`fill="${hex}"`, 'g'), 'fill="transparent"')
    out = out.replace(new RegExp(`fill='${hex}'`, 'g'), "fill='transparent'")
  }
  return out
}
