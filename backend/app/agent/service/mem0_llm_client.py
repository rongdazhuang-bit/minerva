"""Minimal OpenAI-compatible chat client using ``MEM0_LLM_*`` settings."""

from __future__ import annotations

from app.core.log import get_logger

import httpx

from app.config import settings

log = get_logger(__name__)


def mem0_llm_complete(
    *,
    user_prompt: str,
    system_prompt: str = "You are a helpful assistant.",
    max_tokens: int = 1024,
) -> str:
    """Call mem0-configured LLM for one-shot text completion."""

    api_key = (settings.mem0_llm_api_key or "").strip()
    model = (settings.mem0_llm_model or "").strip() or "gpt-4o-mini"
    if not api_key:
        raise ValueError("MEM0_LLM_API_KEY is required for memory compression")

    base = (settings.mem0_llm_base_url or "https://api.openai.com/v1").rstrip("/")
    url = f"{base}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    try:
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        log.warning("mem0 LLM unexpected response: {}", data)
        raise ValueError("mem0 LLM returned an unexpected response") from e
