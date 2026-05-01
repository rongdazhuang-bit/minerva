"""Registers concrete ``ChatCompletionStrategy`` implementations per ``ProviderKind``."""

from app.ai_api.domain.models import ProviderKind
from app.ai_api.strategies.aliyun_placeholder import AliyunPlaceholderStrategy
from app.ai_api.strategies.base import ChatCompletionStrategy
from app.ai_api.strategies.openai_compatible import OpenAICompatibleStrategy
from app.ai_api.strategies.volcengine_placeholder import VolcenginePlaceholderStrategy

__all__ = [
    "AliyunPlaceholderStrategy",
    "ChatCompletionStrategy",
    "OpenAICompatibleStrategy",
    "VolcenginePlaceholderStrategy",
    "get_strategy",
]

_STRATEGIES: dict[str, ChatCompletionStrategy] = {  # Concrete singletons keyed by ``ProviderKind``.
    "openai_compatible": OpenAICompatibleStrategy(),
    "volcengine": VolcenginePlaceholderStrategy(),
    "aliyun": AliyunPlaceholderStrategy(),
}


def get_strategy(provider_kind: ProviderKind | str) -> ChatCompletionStrategy:
    """Resolve strategy singleton or raise ``AppError`` when vendor unsupported."""

    key = provider_kind.value if isinstance(provider_kind, ProviderKind) else provider_kind
    if key not in _STRATEGIES:
        from app.exceptions import AppError

        raise AppError(
            "ai.provider.unknown",
            f"Unknown provider_kind: {provider_kind!s}.",
            400,
        )
    return _STRATEGIES[key]
