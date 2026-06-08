/** Shared helpers to map retrieval_model JSON ↔ Ant Design form values (Dify-aligned). */

export type SearchMethod = 'semantic_search' | 'full_text_search' | 'hybrid_search'

export type RerankingMode = 'weighted_score' | 'reranking_model'

export type RetrievalFormValues = {
  search_method?: SearchMethod
  reranking_enable?: boolean
  reranking_mode?: RerankingMode
  reranking_model_key?: string
  vector_weight?: number
  keyword_weight?: number
  top_k?: number
  score_threshold_enabled?: boolean
  score_threshold?: number
}

/** Split ``provider::model`` composite key into Dify reranking_model fields. */
export function parseRerankKey(key?: string) {
  if (!key?.includes('::')) {
    return { reranking_provider_name: '', reranking_model_name: '' }
  }
  const [provider, model] = key.split('::', 2)
  return { reranking_provider_name: provider, reranking_model_name: model }
}

/** Build composite select value from saved retrieval_model.reranking_model. */
export function toRerankKey(retrieval: Record<string, unknown> | undefined) {
  const cfg = (retrieval?.reranking_model ?? {}) as Record<string, unknown>
  const provider = String(cfg.reranking_provider_name ?? '').trim()
  const model = String(cfg.reranking_model_name ?? '').trim()
  return provider && model ? `${provider}::${model}` : undefined
}

/** Default retrieval form values aligned with backend DEFAULT_RETRIEVAL_MODEL. */
export function defaultRetrievalFormValues(): Partial<RetrievalFormValues> {
  return {
    search_method: 'semantic_search',
    reranking_enable: false,
    reranking_mode: 'reranking_model',
    top_k: 3,
    score_threshold_enabled: false,
    score_threshold: 0.5,
    vector_weight: 0.7,
    keyword_weight: 0.3,
  }
}

/** Hydrate retrieval fields from a saved retrieval_model payload. */
export function parseRetrievalModelToForm(
  retrieval: Record<string, unknown> | null | undefined,
): Partial<RetrievalFormValues> {
  if (!retrieval) return defaultRetrievalFormValues()
  const weights = (retrieval.weights ?? {}) as Record<string, unknown>
  const vectorSetting = (weights.vector_setting ?? {}) as Record<string, unknown>
  const keywordSetting = (weights.keyword_setting ?? {}) as Record<string, unknown>
  const method = String(retrieval.search_method ?? 'semantic_search') as SearchMethod
  return {
    search_method: method,
    reranking_enable: Boolean(retrieval.reranking_enable),
    reranking_mode: (retrieval.reranking_mode as RerankingMode | undefined) ?? 'reranking_model',
    reranking_model_key: toRerankKey(retrieval),
    vector_weight: vectorSetting.vector_weight != null ? Number(vectorSetting.vector_weight) : 0.7,
    keyword_weight: keywordSetting.keyword_weight != null ? Number(keywordSetting.keyword_weight) : 0.3,
    top_k: retrieval.top_k != null ? Number(retrieval.top_k) : 3,
    score_threshold_enabled: Boolean(retrieval.score_threshold_enabled),
    score_threshold: retrieval.score_threshold != null ? Number(retrieval.score_threshold) : 0.5,
  }
}

/** Build Dify-compatible retrieval_model payload from form values. */
export function buildRetrievalModel(
  values: RetrievalFormValues,
  defaultRetrieval: Record<string, unknown> = {},
): Record<string, unknown> {
  const rerank = parseRerankKey(values.reranking_model_key)
  const searchMethod = values.search_method ?? 'semantic_search'
  const rerankingMode =
    values.reranking_mode ??
    (String(defaultRetrieval.reranking_mode ?? '') || 'reranking_model')

  const useWeightedScore = searchMethod === 'hybrid_search' && rerankingMode === 'weighted_score'

  return {
    search_method: searchMethod,
    reranking_enable: values.reranking_enable === true,
    reranking_mode: rerankingMode,
    reranking_model: {
      reranking_provider_name: rerank.reranking_provider_name,
      reranking_model_name: rerank.reranking_model_name,
    },
    weights: useWeightedScore
      ? {
          vector_setting: { vector_weight: values.vector_weight ?? 0.7 },
          keyword_setting: { keyword_weight: values.keyword_weight ?? 0.3 },
        }
      : null,
    top_k: values.top_k ?? Number(defaultRetrieval.top_k ?? 3),
    score_threshold_enabled: values.score_threshold_enabled === true,
    score_threshold: values.score_threshold ?? Number(defaultRetrieval.score_threshold ?? 0.5),
  }
}
