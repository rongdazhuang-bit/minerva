/**
 * Monaco-based editor for agent skill text files (.md, .py, .json).
 */
import Editor from '@monaco-editor/react'

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
}

/**
 * Renders a full-height Monaco editor for skill text files with language derived from `path`.
 */
export function SkillFileEditor({ path, value, onChange, readOnly }: SkillFileEditorProps) {
  const ext = path.slice(path.lastIndexOf('.')).toLowerCase()
  const language = LANG_BY_EXT[ext] ?? 'plaintext'

  return (
    <Editor
      height="100%"
      language={language}
      value={value}
      onChange={(v) => onChange(v ?? '')}
      options={{ readOnly, minimap: { enabled: false }, wordWrap: 'on' }}
    />
  )
}
