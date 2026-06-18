/**
 * Monaco-based editor for agent skill text files (.md, .py, .json).
 */
import Editor, { type BeforeMount } from '@monaco-editor/react'
import { useEffect, useRef, useState } from 'react'
import { MINERVA_TONE_EVENT } from '@/features/auth/authTheme'
import './SkillFileEditor.css'

/** Vertical/horizontal Monaco scrollbar width — matches `minerva-scrollbar-thin` (4px). */
const MONACO_SCROLLBAR_SIZE = 4

/** Shared Monaco options; scrollbar size aligns with app thin scrollbar tokens. */
const BASE_EDITOR_OPTIONS = {
  minimap: { enabled: false },
  wordWrap: 'on' as const,
  scrollBeyondLastLine: false,
  automaticLayout: true,
  scrollbar: {
    verticalScrollbarSize: MONACO_SCROLLBAR_SIZE,
    horizontalScrollbarSize: MONACO_SCROLLBAR_SIZE,
    verticalSliderSize: MONACO_SCROLLBAR_SIZE,
    horizontalSliderSize: MONACO_SCROLLBAR_SIZE,
    useShadows: false,
    arrowSize: 0,
  },
}

/** Registers Minerva editor themes with thin-scrollbar slider colors. */
const registerMinervaMonacoThemes: BeforeMount = (monaco) => {
  monaco.editor.defineTheme('minerva-dark', {
    base: 'vs-dark',
    inherit: true,
    rules: [],
    colors: {
      'scrollbarSlider.background': '#94a3b870',
      'scrollbarSlider.hoverBackground': '#7dd3fc9e',
      'scrollbarSlider.activeBackground': '#7dd3fc9e',
    },
  })
  monaco.editor.defineTheme('minerva-light', {
    base: 'vs',
    inherit: true,
    rules: [],
    colors: {
      'scrollbarSlider.background': '#64748b61',
      'scrollbarSlider.hoverBackground': '#3b82f680',
      'scrollbarSlider.activeBackground': '#3b82f680',
    },
  })
}

/** Maps skill file extensions to Monaco language identifiers. */
const LANG_BY_EXT: Record<string, string> = {
  '.py': 'python',
  '.md': 'markdown',
  '.json': 'json',
}

type SkillFileEditorProps = {
  /** Relative path within the skill package; used to pick syntax highlighting. */
  path: string
  /** Current file buffer shown in the editor. */
  value: string
  /** Called when the user edits buffer content (empty string if cleared). */
  onChange: (value: string) => void
  /** When true, the buffer is view-only (no edits). */
  readOnly?: boolean
  /** Bumps layout measurement when parent visibility changes (e.g. tab switch). */
  layoutKey?: string | number
}

/**
 * Returns Monaco theme id matching the active Minerva UI tone on ``<html>``.
 */
function resolveMonacoTheme(): 'minerva-light' | 'minerva-dark' {
  if (typeof document === 'undefined') return 'minerva-dark'
  return document.documentElement.classList.contains('minerva-tone-sunshine') ? 'minerva-light' : 'minerva-dark'
}

/**
 * Renders a full-height Monaco editor for skill text files with language derived from `path`.
 */
export function SkillFileEditor({ path, value, onChange, readOnly, layoutKey }: SkillFileEditorProps) {
  const ext = path.slice(path.lastIndexOf('.')).toLowerCase()
  const language = LANG_BY_EXT[ext] ?? 'plaintext'
  const containerRef = useRef<HTMLDivElement>(null)
  const [editorHeight, setEditorHeight] = useState(320)
  const [monacoTheme, setMonacoTheme] = useState(resolveMonacoTheme)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const updateHeight = () => {
      const next = Math.max(240, Math.floor(el.getBoundingClientRect().height))
      if (next > 0) setEditorHeight(next)
    }

    updateHeight()
    const ro = new ResizeObserver(updateHeight)
    ro.observe(el)
    return () => ro.disconnect()
  }, [layoutKey])

  useEffect(() => {
    setMonacoTheme(resolveMonacoTheme())
    const onToneChange = () => setMonacoTheme(resolveMonacoTheme())
    window.addEventListener(MINERVA_TONE_EVENT, onToneChange)
    return () => window.removeEventListener(MINERVA_TONE_EVENT, onToneChange)
  }, [])

  return (
    <div ref={containerRef} className="skill-file-editor">
      <Editor
        beforeMount={registerMinervaMonacoThemes}
        height={editorHeight}
        theme={monacoTheme}
        language={language}
        value={value}
        onChange={(v) => onChange(v ?? '')}
        options={{
          ...BASE_EDITOR_OPTIONS,
          readOnly,
        }}
      />
    </div>
  )
}
