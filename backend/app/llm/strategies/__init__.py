"""LLM strategy registry."""

from app.llm.strategies.embedding import EmbeddingStrategy
from app.llm.strategies.rerank import RerankStrategy
from app.llm.strategies.text_chat import TextChatStrategy

_TEXT_CHAT_STRATEGY = TextChatStrategy()
_EMBEDDING_STRATEGY = EmbeddingStrategy()
_RERANK_STRATEGY = RerankStrategy()

__all__ = [
    "EmbeddingStrategy",
    "RerankStrategy",
    "TextChatStrategy",
    "get_embedding_strategy",
    "get_rerank_strategy",
    "get_text_chat_strategy",
]


def get_text_chat_strategy() -> TextChatStrategy:
    """Return singleton text chat strategy."""

    return _TEXT_CHAT_STRATEGY


def get_embedding_strategy() -> EmbeddingStrategy:
    """Return singleton embedding strategy."""

    return _EMBEDDING_STRATEGY


def get_rerank_strategy() -> RerankStrategy:
    """Return singleton rerank strategy."""

    return _RERANK_STRATEGY
