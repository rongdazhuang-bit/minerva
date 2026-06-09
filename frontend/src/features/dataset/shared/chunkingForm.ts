/** Shared helpers to map process_rule JSON ↔ Ant Design form values (Dify-aligned). */

export type ParentModeType = 'paragraph' | 'full-doc'

export type ChunkingFormValues = {
  doc_form?: 'text_model' | 'hierarchical_model' | 'qa_model'
  delimiter?: string
  max_length?: number
  chunk_overlap?: number
  parent_mode_type?: ParentModeType
  parent_delimiter?: string
  parent_max_length?: number
  parent_chunk_overlap?: number
  sub_delimiter?: string
  sub_max_length?: number
  sub_chunk_overlap?: number
  remove_extra_spaces?: boolean
  remove_urls_emails?: boolean
  recognize_formula?: boolean
  recognize_table?: boolean
  use_qa_segmentation?: boolean
  qa_language?: string
}

type PreRule = { id: string; enabled: boolean }

type SegBlock = Record<string, unknown>

function rulesDict(processRule: Record<string, unknown>) {
  return (processRule.rules as Record<string, unknown> | undefined) ?? {}
}

function ruleBlock(rules: Record<string, unknown>, key: string) {
  const block = rules[key]
  return block && typeof block === 'object' && !Array.isArray(block) ? (block as SegBlock) : {}
}

function preRuleEnabled(rules: Record<string, unknown>, ruleId: string, defaultEnabled: boolean) {
  const list = rules.pre_processing_rules
  if (!Array.isArray(list)) return defaultEnabled
  const row = list.find((item) => (item as PreRule).id === ruleId) as PreRule | undefined
  return row?.enabled !== false
}

/** Read delimiter from Dify ``separator`` or legacy ``delimiter``. */
function readSeparator(block: SegBlock, fallback: string) {
  if (block.separator != null) return String(block.separator)
  if (block.delimiter != null) return String(block.delimiter)
  return fallback
}

/** Read max length from Dify ``max_tokens`` or legacy ``max_length``. */
function readMaxTokens(block: SegBlock, fallback: number) {
  if (block.max_tokens != null) return Number(block.max_tokens)
  if (block.max_length != null) return Number(block.max_length)
  return fallback
}

function readOverlap(block: SegBlock, fallback: number) {
  if (block.chunk_overlap != null) return Number(block.chunk_overlap)
  return fallback
}

function readParentMode(rules: Record<string, unknown>): ParentModeType {
  const raw = rules.parent_mode ?? rules.parent_mode_type
  if (raw === 'full-doc' || raw === 'paragraph') return raw
  if (typeof raw === 'object' && raw != null) {
    const mode = (raw as SegBlock).mode
    if (mode === 'full-doc' || mode === 'paragraph') return mode
  }
  return 'paragraph'
}

/** Default parent/child field values (always hydrated so mode switches show values). */
function readHierarchicalFormFields(
  rules: Record<string, unknown>,
): Pick<
  ChunkingFormValues,
  | 'parent_mode_type'
  | 'parent_delimiter'
  | 'parent_max_length'
  | 'parent_chunk_overlap'
  | 'sub_delimiter'
  | 'sub_max_length'
  | 'sub_chunk_overlap'
> {
  const seg = ruleBlock(rules, 'segmentation')
  const sub = ruleBlock(rules, 'subchunk_segmentation')
  return {
    parent_mode_type: readParentMode(rules),
    parent_delimiter: readSeparator(seg, '\\n\\n'),
    parent_max_length: readMaxTokens(seg, 1024),
    parent_chunk_overlap: readOverlap(seg, 100),
    sub_delimiter: readSeparator(sub, '\\n'),
    sub_max_length: readMaxTokens(sub, 512),
    sub_chunk_overlap: readOverlap(sub, 50),
  }
}

/** Hydrate chunking fields from a saved process_rule payload. */
export function parseProcessRuleToForm(processRule: Record<string, unknown> | null | undefined) {
  if (!processRule) return {}
  const rules = rulesDict(processRule)
  const seg = ruleBlock(rules, 'segmentation')
  const hierarchical = readHierarchicalFormFields(rules)
  const mode = String(processRule.mode ?? 'custom')
  const docForm =
    mode === 'hierarchical'
      ? 'hierarchical_model'
      : seg.qa_enabled === true
        ? 'qa_model'
        : 'text_model'

  return {
    doc_form: docForm as ChunkingFormValues['doc_form'],
    delimiter: readSeparator(seg, '\\n\\n'),
    max_length: readMaxTokens(seg, 1024),
    chunk_overlap: readOverlap(seg, 50),
    ...hierarchical,
    remove_extra_spaces: preRuleEnabled(rules, 'remove_extra_spaces', true),
    remove_urls_emails: preRuleEnabled(rules, 'remove_urls_emails', true),
    recognize_formula: preRuleEnabled(rules, 'recognize_formula', false),
    recognize_table: preRuleEnabled(rules, 'recognize_table', false),
    use_qa_segmentation: docForm === 'qa_model',
    qa_language: seg.qa_language != null ? String(seg.qa_language) : 'Chinese Simplified',
  } satisfies Partial<ChunkingFormValues>
}

/** Default chunking field values from API default process rule. */
export function defaultChunkingFormValues(defaultRule: Record<string, unknown>): Partial<ChunkingFormValues> {
  return {
    doc_form: 'text_model',
    use_qa_segmentation: false,
    qa_language: 'Chinese Simplified',
    ...parseProcessRuleToForm(defaultRule),
  }
}

function buildSegBlock(
  separator: string,
  maxTokens: number,
  chunkOverlap?: number,
): Record<string, unknown> {
  const block: Record<string, unknown> = {
    separator,
    max_tokens: maxTokens,
  }
  if (chunkOverlap != null) {
    block.chunk_overlap = chunkOverlap
  }
  return block
}

/** Build Dify-compatible process_rule payload from form values. */
export function buildProcessRule(values: ChunkingFormValues, defaultRule: Record<string, unknown>) {
  const rules = rulesDict(defaultRule)
  const segmentation = ruleBlock(rules, 'segmentation')
  const subDefault = ruleBlock(rules, 'subchunk_segmentation')

  const docForm =
    values.doc_form ??
    (values.use_qa_segmentation ? 'qa_model' : 'text_model')

  const isHierarchical = docForm === 'hierarchical_model'
  const parentMode = values.parent_mode_type ?? 'paragraph'

  const generalSeparator = values.delimiter ?? readSeparator(segmentation, '\\n\\n')
  const generalMaxTokens = values.max_length ?? readMaxTokens(segmentation, 1024)
  const generalOverlap = values.chunk_overlap ?? readOverlap(segmentation, 50)

  const rulesOut: Record<string, unknown> = {
    pre_processing_rules: [
      { id: 'remove_extra_spaces', enabled: values.remove_extra_spaces !== false },
      { id: 'remove_urls_emails', enabled: values.remove_urls_emails !== false },
      { id: 'recognize_formula', enabled: values.recognize_formula === true },
      { id: 'recognize_table', enabled: values.recognize_table === true },
    ],
  }

  if (isHierarchical) {
    rulesOut.parent_mode = parentMode
    if (parentMode === 'paragraph') {
      rulesOut.segmentation = buildSegBlock(
        values.parent_delimiter ?? readSeparator(segmentation, '\\n\\n'),
        values.parent_max_length ?? readMaxTokens(segmentation, 1024),
        values.parent_chunk_overlap ?? readOverlap(segmentation, 100),
      )
    }
    rulesOut.subchunk_segmentation = buildSegBlock(
      values.sub_delimiter ?? readSeparator(subDefault, '\\n'),
      values.sub_max_length ?? readMaxTokens(subDefault, 512),
      values.sub_chunk_overlap ?? readOverlap(subDefault, 50),
    )
  } else {
    rulesOut.segmentation = buildSegBlock(generalSeparator, generalMaxTokens, generalOverlap)
  }

  return {
    mode: isHierarchical ? 'hierarchical' : 'custom',
    rules: rulesOut,
  }
}
