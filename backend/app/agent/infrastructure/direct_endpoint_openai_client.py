"""AsyncOpenAI client that posts chat completions to a configured URL verbatim."""

from __future__ import annotations

from urllib.parse import urlparse

from openai import AsyncOpenAI

from app.llm.strategies.openai_compatible import normalize_openai_base_url

_CHAT_COMPLETIONS_PATH = "/chat/completions"


def build_direct_endpoint_async_openai(*, endpoint_url: str, api_key: str) -> AsyncOpenAI:
    """Return AsyncOpenAI whose chat completion requests use ``endpoint_url`` as-is."""

    target = normalize_openai_base_url(endpoint_url)
    parsed = urlparse(target)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    client = AsyncOpenAI(api_key=api_key, base_url=origin)

    original_post = client.post

    async def post(path: str, *args, **kwargs):
        """Route relative chat completion paths to the configured absolute URL."""

        normalized = path.rstrip("/")
        request_path = path
        if normalized == _CHAT_COMPLETIONS_PATH or normalized.endswith(_CHAT_COMPLETIONS_PATH):
            request_path = target
        return await original_post(request_path, *args, **kwargs)

    client.post = post  # type: ignore[method-assign]
    return client
