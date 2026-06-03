"""Build mem0 embedder config and expose endpoint metadata for logging."""

from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger(__name__)

_resolved_embedder: tuple[str, str, bool] | None = None


def normalize_openai_embedder_base_url(url: str) -> str:
    """Ensure OpenAI-compatible embedding root ends with ``/v1``."""

    normalized = url.strip().rstrip("/")
    if not normalized:
        return ""
    if normalized.endswith("/v1"):
        return normalized
    return f"{normalized}/v1"


def resolve_mem0_embedder_api_base(*, allow_llm_fallback: bool = True) -> str:
    """Return configured OpenAI-compatible embedding API base (no trailing slash)."""

    from app.config import settings

    direct = settings.mem0_embedder_direct_base_url.strip()
    if direct:
        return normalize_openai_embedder_base_url(direct)
    base = settings.mem0_embedder_base_url.strip()
    if base:
        return normalize_openai_embedder_base_url(base)
    if allow_llm_fallback:
        llm_base = settings.mem0_llm_base_url.strip()
        if llm_base:
            return normalize_openai_embedder_base_url(llm_base)
    return ""


def resolve_mem0_embedder_api_key(*, allow_llm_fallback: bool = True) -> str:
    """Return configured embedder API key, optionally falling back to ``MEM0_LLM_API_KEY``."""

    from app.config import settings

    key = settings.mem0_embedder_api_key.strip()
    if key:
        return key
    if allow_llm_fallback:
        return settings.mem0_llm_api_key.strip()
    return ""


def probe_embedder_endpoint(*, base_url: str, api_key: str, model: str) -> bool:
    """Return True when ``base_url`` accepts an OpenAI-compatible embeddings request."""

    if not base_url.strip():
        return False

    from app.config import settings

    url = f"{base_url.rstrip('/')}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model.strip() or "text-embedding-3-small",
        "input": "ping",
    }
    timeout = httpx.Timeout(
        connect=min(settings.ai_http_connect_timeout, 2.0),
        read=min(settings.ai_http_read_timeout, 15.0),
        write=min(settings.ai_http_read_timeout, 15.0),
        pool=min(settings.ai_http_connect_timeout, 2.0),
    )
    from app.agent.memory.mem0.logging_embedder import (
        log_embedder_request,
        log_embedder_response,
        make_probe_embedder_stand_in,
    )

    probe_inner = make_probe_embedder_stand_in(base_url=base_url, model=model)
    log_embedder_request(inner=probe_inner, inputs=["ping"], memory_action="probe")
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.post(url, json=payload, headers=headers)
        ok = resp.status_code < 500
        extra: dict[str, Any] = {"status_code": resp.status_code}
        vectors: list[list[float]] = []
        if ok:
            try:
                data = resp.json()
                vectors = [item.get("embedding") or [] for item in data.get("data") or []]
                if isinstance(data.get("usage"), dict):
                    extra["usage"] = data["usage"]
                if data.get("model"):
                    extra["model"] = data["model"]
            except ValueError:
                extra["raw_response"] = resp.text[: settings.log_body_max_chars]
        else:
            extra["raw_response"] = resp.text[: settings.log_body_max_chars]
        log_embedder_response(inner=probe_inner, vectors=vectors, extra=extra)
        if not ok:
            log.warning(
                "mem0 embedder probe failed url=%s status=%s",
                url,
                resp.status_code,
            )
        return ok
    except (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError, OSError) as exc:
        log_embedder_response(inner=probe_inner, vectors=[], extra={"status_code": None, "error": str(exc)})
        log.warning("mem0 embedder probe transport error url=%s error=%s", url, exc)
        return False


def resolve_working_embedder_credentials() -> tuple[str, str, bool]:
    """Return ``(base_url, api_key, used_llm_fallback)`` after optional reachability probe."""

    global _resolved_embedder
    if _resolved_embedder is not None:
        return _resolved_embedder

    from app.config import settings

    model = settings.mem0_embedder_model.strip()
    configured_base = resolve_mem0_embedder_api_base(allow_llm_fallback=False)
    configured_key = resolve_mem0_embedder_api_key(allow_llm_fallback=False)
    llm_base = normalize_openai_embedder_base_url(settings.mem0_llm_base_url.strip())
    llm_key = settings.mem0_llm_api_key.strip()

    if configured_base and probe_embedder_endpoint(
        base_url=configured_base,
        api_key=configured_key or llm_key,
        model=model,
    ):
        _resolved_embedder = (configured_base, configured_key or llm_key, False)
        return _resolved_embedder

    if configured_base and llm_base and llm_base != configured_base:
        if probe_embedder_endpoint(base_url=llm_base, api_key=llm_key, model=model):
            log.warning(
                "mem0 embedder unreachable at %s; using MEM0_LLM_BASE_URL=%s",
                configured_base,
                llm_base,
            )
            _resolved_embedder = (llm_base, llm_key, True)
            return _resolved_embedder

    if not configured_base and llm_base:
        _resolved_embedder = (llm_base, llm_key, True)
        return _resolved_embedder

    fallback_base = configured_base or llm_base
    fallback_key = configured_key or llm_key
    _resolved_embedder = (fallback_base, fallback_key, not configured_base and bool(llm_base))
    return _resolved_embedder


def build_embedder_config() -> dict[str, Any]:
    """Build mem0 ``embedder.config`` with provider-specific base URL keys."""

    from app.config import settings

    provider = settings.mem0_embedder_provider.strip().lower()
    model = settings.mem0_embedder_model.strip()
    base, api_key, _ = resolve_working_embedder_credentials()
    cfg: dict[str, Any] = {
        "model": model or None,
        "api_key": api_key or None,
    }
    if not base:
        return cfg

    if provider == "ollama":
        cfg["ollama_base_url"] = base.removesuffix("/v1").rstrip("/") or base
    elif provider == "huggingface":
        cfg["huggingface_base_url"] = base
    elif provider == "lmstudio":
        cfg["lmstudio_base_url"] = base
    else:
        cfg["openai_base_url"] = base
    return cfg


def mem0_embedder_endpoint_summary() -> str:
    """Short embedder target description for logs (no secrets)."""

    from app.config import settings

    model = settings.mem0_embedder_model.strip() or "(default)"
    base, _, used_llm_fallback = resolve_working_embedder_credentials()
    if not base:
        base = "(default-openai)"
    if used_llm_fallback:
        via = "llm_fallback"
    elif settings.mem0_embedder_direct_base_url.strip():
        via = "direct"
    else:
        via = "base"
    return f"provider={settings.mem0_embedder_provider} model={model} {via}_url={base}"
