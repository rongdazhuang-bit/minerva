"""Registers concrete ``ChatCompletionStrategy`` implementations per ``ProviderKind``."""

from app.llm.domain.models import ProviderKind
from app.llm.strategies.aliyun_compatible import AliyunCompatibleStrategy
from app.llm.strategies.base import ChatCompletionStrategy
from app.llm.strategies.openai_compatible import OpenAICompatibleStrategy
from app.llm.strategies.volcengine_compatible import VolcengineCompatibleStrategy

__all__ = [
    "AliyunCompatibleStrategy",
    "ChatCompletionStrategy",
    "OpenAICompatibleStrategy",
    "VolcengineCompatibleStrategy",
    "get_strategy",
]

_STRATEGIES: dict[str, ChatCompletionStrategy] = {  # Concrete singletons keyed by ``ProviderKind``.
    "openai": OpenAICompatibleStrategy(),
    "volcengine": VolcengineCompatibleStrategy(),
    "aliyun": AliyunCompatibleStrategy(),
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
