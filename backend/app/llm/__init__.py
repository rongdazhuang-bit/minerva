"""Multi-capability LLM module with model_id-centric invocation."""

from app.llm.domain.models import (
    ChatMessage,
    EmbeddingCallParams,
    EmbeddingResult,
    RerankCallParams,
    RerankResult,
    TextChatCallParams,
    TextChatResult,
)
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.service.llm_service import LlmService, build_openai_messages, llm_service

__all__ = [
    "ChatMessage",
    "EmbeddingCallParams",
    "EmbeddingResult",
    "LlmService",
    "RerankCallParams",
    "RerankResult",
    "ResolvedModel",
    "TextChatCallParams",
    "TextChatResult",
    "build_openai_messages",
    "llm_service",
]
