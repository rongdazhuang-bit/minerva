/** Allowed source file extensions for knowledge base uploads (aligned with backend). */

export const DATASET_ALLOWED_EXTENSIONS = [
  'markdown',
  'mdx',
  'vtt',
  'properties',
  'docx',
  'htm',
  'md',
  'pdf',
  'xls',
  'xlsx',
  'html',
  'txt',
  'csv',
] as const

export type DatasetAllowedExtension = (typeof DATASET_ALLOWED_EXTENSIONS)[number]

const EXTENSION_SET = new Set<string>(DATASET_ALLOWED_EXTENSIONS)

/** Return true when the filename extension is allowed for dataset upload. */
export function isDatasetAllowedExtension(fileName: string): boolean {
  const ext = fileName.split('.').pop()?.toLowerCase()
  return Boolean(ext && EXTENSION_SET.has(ext))
}

/** Value for `<Upload accept="…">` file picker filter. */
export const DATASET_UPLOAD_ACCEPT = DATASET_ALLOWED_EXTENSIONS.map((ext) => `.${ext}`).join(',')
