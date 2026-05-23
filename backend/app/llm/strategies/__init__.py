"""Register the unified OpenAI-compatible chat completion strategy."""

from app.llm.domain.models import ProviderKind
from app.llm.strategies.base import ChatCompletionStrategy
from app.llm.strategies.openai_compatible import OpenAICompatibleStrategy
from app.exceptions import AppError

__all__ = [
    "ChatCompletionStrategy",
    "OpenAICompatibleStrategy",
    "get_strategy",
]

_OPENAI_COMPATIBLE_STRATEGY = OpenAICompatibleStrategy()
_COMPATIBLE_PROVIDER_KINDS = frozenset(
    {
        ProviderKind.openai.value,
        ProviderKind.volcengine.value,
        ProviderKind.aliyun.value,
    }
)


def get_strategy(provider_kind: ProviderKind | str = ProviderKind.openai) -> ChatCompletionStrategy:
    """Return the unified strategy for supported legacy provider values."""

    key = provider_kind.value if isinstance(provider_kind, ProviderKind) else provider_kind
    if key not in _COMPATIBLE_PROVIDER_KINDS:
        raise AppError(
            "ai.provider.unknown",
            f"Unknown provider_kind: {provider_kind!s}.",
            400,
        )
    return _OPENAI_COMPATIBLE_STRATEGY
