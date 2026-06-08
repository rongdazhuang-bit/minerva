"""Domain constants for knowledge base indexing and retrieval."""

from __future__ import annotations

INDEXING_TECHNIQUE_HIGH_QUALITY = "high_quality"
INDEXING_TECHNIQUE_ECONOMY = "economy"

INDEXING_STATUS_WAITING = "waiting"
INDEXING_STATUS_PARSING = "parsing"
INDEXING_STATUS_CLEANING = "cleaning"
INDEXING_STATUS_SPLITTING = "splitting"
INDEXING_STATUS_INDEXING = "indexing"
INDEXING_STATUS_COMPLETED = "completed"
INDEXING_STATUS_ERROR = "error"

RETRIEVAL_SEMANTIC = "semantic_search"
RETRIEVAL_FULL_TEXT = "full_text_search"
RETRIEVAL_HYBRID = "hybrid_search"

DOC_FORM_TEXT = "text_model"
DOC_FORM_HIERARCHICAL = "hierarchical_model"
DOC_FORM_QA = "qa_model"

PROCESS_MODE_AUTOMATIC = "automatic"
PROCESS_MODE_CUSTOM = "custom"
PROCESS_MODE_HIERARCHICAL = "hierarchical"

DATA_SOURCE_UPLOAD_FILE = "upload_file"

DEFAULT_KEYWORD_NUMBER = 10

DATASET_INDEXING_TASK_NAME = "dataset.document_indexing"

DATASET_ALLOWED_EXTENSIONS = frozenset(
    {
        "txt",
        "md",
        "markdown",
        "mdx",
        "pdf",
        "docx",
        "html",
        "htm",
        "csv",
        "xls",
        "xlsx",
        "vtt",
        "properties",
    }
)

DEFAULT_PROCESS_RULE: dict = {
    "mode": PROCESS_MODE_CUSTOM,
    "rules": {
        "pre_processing_rules": [
            {"id": "remove_extra_spaces", "enabled": True},
            {"id": "remove_urls_emails", "enabled": True},
        ],
        "segmentation": {
            "separator": "\\n\\n",
            "max_tokens": 1024,
            "chunk_overlap": 50,
        },
        "parent_mode": "paragraph",
        "subchunk_segmentation": {
            "separator": "\\n",
            "max_tokens": 512,
            "chunk_overlap": 50,
        },
    },
}

DEFAULT_RETRIEVAL_MODEL: dict = {
    "search_method": RETRIEVAL_SEMANTIC,
    "reranking_enable": False,
    "reranking_mode": "reranking_model",
    "reranking_model": {"reranking_provider_name": "", "reranking_model_name": ""},
    "weights": None,
    "top_k": 3,
    "score_threshold_enabled": False,
    "score_threshold": 0.5,
}
