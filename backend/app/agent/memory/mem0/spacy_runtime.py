"""Ensure mem0 spaCy models are installed before entity/BM25 helpers run."""

from __future__ import annotations

from app.core.log import get_logger

log = get_logger(__name__)

_MEM0_NLP_INSTALL_HINT = (
    'Install NLP deps with: cd backend && pip install -e ".[dev]" '
    '(includes mem0ai[nlp] / spacy).'
)
_SPACY_MODEL = "en_core_web_sm"


def ensure_mem0_spacy_ready() -> None:
    """Load spaCy and ``en_core_web_sm``; raise if mem0 NLP helpers cannot run."""

    try:
        import spacy  # noqa: F401
    except ModuleNotFoundError as e:
        raise RuntimeError(
            f"AGENT_MEMORY_BACKEND=mem0 requires spaCy for mem0 NLP features. {_MEM0_NLP_INSTALL_HINT}"
        ) from e

    from mem0.utils.spacy_models import get_nlp_full, get_nlp_lemma

    full = get_nlp_full()
    lemma = get_nlp_lemma()
    if full is None or lemma is None:
        raise RuntimeError(
            f"mem0 spaCy model {_SPACY_MODEL!r} is unavailable. "
            f"Run: python -m spacy download {_SPACY_MODEL}"
        )
    log.info("mem0 spaCy models ready model={}", _SPACY_MODEL)
