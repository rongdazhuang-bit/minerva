/**
 * 围栏代码块 `` ```lang `` 与 Prism 注册名对齐；未列出则原样传入（Prism 不识别时由渲染层回退）。
 */
const PRISM_LANG_ALIASES: Record<string, string> = {
  ts: 'typescript',
  tsx: 'tsx',
  js: 'javascript',
  jsx: 'jsx',
  mjs: 'javascript',
  cjs: 'javascript',
  py: 'python',
  python3: 'python',
  rb: 'ruby',
  rs: 'rust',
  sh: 'bash',
  shell: 'bash',
  zsh: 'bash',
  bash: 'bash',
  yml: 'yaml',
  yaml: 'yaml',
  md: 'markdown',
  json: 'json',
  jsonc: 'json',
  html: 'markup',
  htm: 'markup',
  xml: 'markup',
  svg: 'markup',
  vue: 'markup',
  cpp: 'cpp',
  'c++': 'cpp',
  cxx: 'cpp',
  cc: 'cpp',
  c: 'c',
  h: 'cpp',
  csharp: 'csharp',
  cs: 'csharp',
  kt: 'kotlin',
  kts: 'kotlin',
  swift: 'swift',
  sql: 'sql',
  ps1: 'powershell',
  pwsh: 'powershell',
  powershell: 'powershell',
  dockerfile: 'docker',
  docker: 'docker',
  diff: 'diff',
  patch: 'diff',
  go: 'go',
  golang: 'go',
  java: 'java',
  scala: 'scala',
  php: 'php',
  r: 'r',
  lua: 'lua',
  perl: 'perl',
  pl: 'perl',
  clj: 'clojure',
  cljs: 'clojure',
  ex: 'elixir',
  exs: 'elixir',
  hs: 'haskell',
  fs: 'fsharp',
  fsharp: 'fsharp',
  vb: 'vbnet',
  dart: 'dart',
  zig: 'zig',
  toml: 'toml',
  ini: 'ini',
  properties: 'properties',
  graphql: 'graphql',
  gql: 'graphql',
}

/** Human-readable labels for Prism language ids (UI badge). */
const PRISM_LANGUAGE_LABELS: Record<string, string> = {
  typescript: 'TypeScript',
  tsx: 'TSX',
  javascript: 'JavaScript',
  jsx: 'JSX',
  python: 'Python',
  ruby: 'Ruby',
  rust: 'Rust',
  bash: 'Bash',
  yaml: 'YAML',
  markdown: 'Markdown',
  json: 'JSON',
  markup: 'HTML',
  cpp: 'C++',
  c: 'C',
  csharp: 'C#',
  kotlin: 'Kotlin',
  swift: 'Swift',
  sql: 'SQL',
  powershell: 'PowerShell',
  docker: 'Dockerfile',
  diff: 'Diff',
  go: 'Go',
  java: 'Java',
  scala: 'Scala',
  php: 'PHP',
  r: 'R',
  lua: 'Lua',
  perl: 'Perl',
  clojure: 'Clojure',
  elixir: 'Elixir',
  haskell: 'Haskell',
  fsharp: 'F#',
  vbnet: 'VB.NET',
  dart: 'Dart',
  zig: 'Zig',
  toml: 'TOML',
  ini: 'INI',
  properties: 'Properties',
  graphql: 'GraphQL',
  plaintext: 'Plain Text',
  text: 'Plain Text',
}

/**
 * Format the language badge for a fenced code block (prefers canonical name over raw fence tag).
 */
export function formatCodeBlockLanguageLabel(
  rawFenceTag: string,
  prismLang: string,
  plainTextLabel = 'Plain Text',
): string {
  const trimmed = rawFenceTag.trim()
  if (trimmed) {
    const normalized = normalizePrismLanguage(trimmed)
    return PRISM_LANGUAGE_LABELS[normalized] ?? trimmed
  }
  if (prismLang === 'plaintext' || prismLang === 'text') {
    return plainTextLabel
  }
  return PRISM_LANGUAGE_LABELS[prismLang] ?? prismLang
}

/** 将 Markdown 围栏语言标签规范为 Prism 语言 id。 */
export function normalizePrismLanguage(raw: string): string {
  const k = raw.toLowerCase().trim()
  return PRISM_LANG_ALIASES[k] ?? k
}
