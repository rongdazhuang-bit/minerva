/** Format step-2 form values for the Dify-style completion summary (step 3). */

import type { TFunction } from 'i18next'
import type { ChunkingFormValues } from '@/features/dataset/shared/chunkingForm'
import type { IndexingFormValues } from '@/features/dataset/create/IndexingMethodPanel'
import type { RetrievalFormValues, SearchMethod } from '@/features/dataset/shared/retrievalForm'

export type CreateCompletionSnapshot = ChunkingFormValues &
  IndexingFormValues &
  RetrievalFormValues

export type CompletionSummaryRow = {
  label: string
  value: string
  icon?: 'indexing' | 'retrieval'
}

/** Human-readable segmentation mode label. */
export function formatSegmentationMode(values: CreateCompletionSnapshot, t: TFunction): string {
  if (values.doc_form === 'hierarchical_model') {
    const parentLabel =
      values.parent_mode_type === 'full-doc'
        ? t('dataset.create.segmentation.parentFullDoc')
        : t('dataset.create.segmentation.parentParagraph')
    return `${t('dataset.create.docForm.hierarchical')} - ${parentLabel}`
  }
  if (values.doc_form === 'qa_model' || values.use_qa_segmentation) {
    return t('dataset.create.docForm.qa')
  }
  return t('dataset.create.docForm.text')
}

/** Human-readable max segment length (parent/child for hierarchical mode). */
export function formatMaxSegmentLength(values: CreateCompletionSnapshot, t: TFunction): string {
  if (values.doc_form === 'hierarchical_model') {
    const parent =
      values.parent_mode_type === 'full-doc'
        ? t('dataset.create.complete.fullDocParent')
        : String(values.parent_max_length ?? values.max_length ?? 1024)
    const child = String(values.sub_max_length ?? 512)
    return t('dataset.create.complete.maxLengthHierarchical', { parent, child })
  }
  return String(values.max_length ?? 1024)
}

/** Enabled preprocessing rules joined for display. */
export function formatPreprocessingRules(values: CreateCompletionSnapshot, t: TFunction): string {
  const parts: string[] = []
  if (values.remove_extra_spaces !== false) {
    parts.push(t('dataset.create.complete.preprocessSpaces'))
  }
  if (values.remove_urls_emails) {
    parts.push(t('dataset.create.field.removeUrls'))
  }
  return parts.length > 0 ? parts.join('、') : t('dataset.create.complete.preprocessNone')
}

/** Indexing technique label. */
export function formatIndexingMethod(values: CreateCompletionSnapshot, t: TFunction): string {
  return values.indexing_technique === 'economy'
    ? t('dataset.indexing.economy')
    : t('dataset.indexing.highQuality')
}

const RETRIEVAL_TITLE_KEYS: Record<SearchMethod, string> = {
  semantic_search: 'dataset.create.retrieval.semantic.title',
  full_text_search: 'dataset.create.retrieval.fullText.title',
  hybrid_search: 'dataset.create.retrieval.hybrid.title',
}

/** Retrieval method label. */
export function formatRetrievalMethod(values: CreateCompletionSnapshot, t: TFunction): string {
  const method = (values.search_method ?? 'semantic_search') as SearchMethod
  return t(RETRIEVAL_TITLE_KEYS[method] ?? RETRIEVAL_TITLE_KEYS.semantic_search)
}

/** Build summary rows shown on the step-3 completion card. */
export function buildCompletionSummaryRows(
  values: CreateCompletionSnapshot,
  t: TFunction,
): CompletionSummaryRow[] {
  return [
    { label: t('dataset.create.complete.segmentationMode'), value: formatSegmentationMode(values, t) },
    { label: t('dataset.create.complete.maxSegmentLength'), value: formatMaxSegmentLength(values, t) },
    { label: t('dataset.create.complete.preprocessRules'), value: formatPreprocessingRules(values, t) },
    {
      label: t('dataset.create.field.indexing'),
      value: formatIndexingMethod(values, t),
      icon: 'indexing',
    },
    {
      label: t('dataset.create.retrieval.title'),
      value: formatRetrievalMethod(values, t),
      icon: 'retrieval',
    },
  ]
}
