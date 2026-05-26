"""Normalize LangChain/OpenAI usage and merge persisted layered usage documents."""



from __future__ import annotations



from typing import Any



OpenAIUsage = dict[str, int]



# Layered persisted usage payloads (flat totals, optional details/by_phase/by_step).

UsageDocument = dict[str, Any]



_STANDARD_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")





def _coerce_non_negative_int(value: Any) -> int | None:

    """Return a non-negative integer token count, or ``None`` when invalid."""



    if value is None or isinstance(value, bool):

        return None

    try:

        n = int(value)

    except (TypeError, ValueError):

        return None

    return n if n >= 0 else None





def _extract_details_from_mapping(raw: dict[str, Any]) -> dict[str, int] | None:

    """Extract optional token detail counts from OpenAI or LangChain usage shapes."""



    details: dict[str, int] = {}



    nested = raw.get("details")

    if isinstance(nested, dict):

        for key, value in nested.items():

            n = _coerce_non_negative_int(value)

            if n is not None:

                details[key] = int(details.get(key, 0)) + n



    prompt_details = raw.get("prompt_tokens_details")

    if isinstance(prompt_details, dict):

        cached = _coerce_non_negative_int(prompt_details.get("cached_tokens"))

        if cached is not None:

            details["cached_tokens"] = int(details.get("cached_tokens", 0)) + cached



    completion_details = raw.get("completion_tokens_details")

    if isinstance(completion_details, dict):

        reasoning = _coerce_non_negative_int(completion_details.get("reasoning_tokens"))

        if reasoning is not None:

            details["reasoning_tokens"] = int(details.get("reasoning_tokens", 0)) + reasoning



    input_details = raw.get("input_token_details")

    if isinstance(input_details, dict):

        cache_read = _coerce_non_negative_int(input_details.get("cache_read"))

        if cache_read is not None:

            details["cached_tokens"] = int(details.get("cached_tokens", 0)) + cache_read



    output_details = raw.get("output_token_details")

    if isinstance(output_details, dict):

        reasoning = _coerce_non_negative_int(output_details.get("reasoning"))

        if reasoning is not None:

            details["reasoning_tokens"] = int(details.get("reasoning_tokens", 0)) + reasoning



    for key, value in raw.items():

        if key in _STANDARD_KEYS or key in ("details", "by_phase", "by_step", "skill_id"):

            continue

        if not key.endswith("_tokens"):

            continue

        n = _coerce_non_negative_int(value)

        if n is not None:

            details[key] = int(details.get(key, 0)) + n



    return details or None





def normalize_openai_usage(raw: Any) -> OpenAIUsage | None:

    """Map LangChain ``usage_metadata`` or OpenAI ``usage`` dict to standard keys.



    OpenAI chat completion ``usage`` object::



        {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}

    """



    if raw is None:

        return None

    if not isinstance(raw, dict):

        return None



    prompt = _coerce_non_negative_int(

        raw.get("prompt_tokens", raw.get("input_tokens"))

    )

    completion = _coerce_non_negative_int(

        raw.get("completion_tokens", raw.get("output_tokens"))

    )

    total = _coerce_non_negative_int(raw.get("total_tokens"))



    if prompt is None and completion is None and total is None:

        return None



    if total is None and prompt is not None and completion is not None:

        total = prompt + completion



    usage: OpenAIUsage = {}

    if prompt is not None:

        usage["prompt_tokens"] = prompt

    if completion is not None:

        usage["completion_tokens"] = completion

    if total is not None:

        usage["total_tokens"] = total

    return usage or None





def usage_document_flat(usage_doc: UsageDocument) -> OpenAIUsage:

    """Return standard token keys from a layered usage document."""



    return {key: int(usage_doc[key]) for key in _STANDARD_KEYS if key in usage_doc}


def reasoning_tokens_from_usage_document(usage_doc: UsageDocument | None) -> int:
    """Return merged ``details.reasoning_tokens`` from a layered usage document."""

    if not usage_doc:
        return 0
    details = usage_doc.get("details")
    if not isinstance(details, dict):
        return 0
    value = details.get("reasoning_tokens")
    n = _coerce_non_negative_int(value)
    return int(n) if n is not None else 0



def usage_document_for_node(usage_doc: UsageDocument) -> dict[str, Any]:

    """Build ``llm.round`` / node ``usage_json`` (standard keys + optional ``details``)."""



    out: dict[str, Any] = usage_document_flat(usage_doc)

    details = usage_doc.get("details")

    if isinstance(details, dict) and details:

        out["details"] = dict(details)

    return out





def _flat_usage_from_langchain_object(output: Any) -> OpenAIUsage | None:
    """Extract flat OpenAI usage from LangChain messages or ``LLMResult``."""

    if output is None:
        return None

    usage_metadata = getattr(output, "usage_metadata", None)
    if isinstance(usage_metadata, dict):
        flat = normalize_openai_usage(usage_metadata)
        if flat:
            return flat

    response_metadata = getattr(output, "response_metadata", None)
    if isinstance(response_metadata, dict):
        token_usage = response_metadata.get("token_usage")
        if isinstance(token_usage, dict):
            flat = normalize_openai_usage(token_usage)
            if flat:
                return flat

    generations = getattr(output, "generations", None)
    if isinstance(generations, list):
        for group in generations:
            if not isinstance(group, list):
                continue
            for generation in group:
                message = getattr(generation, "message", None)
                nested = _flat_usage_from_langchain_object(message)
                if nested:
                    return nested

    return None





def extract_usage_document(raw: Any) -> UsageDocument | None:

    """Normalize one LLM usage payload into a layered document fragment."""



    if raw is None:

        return None



    if isinstance(raw, dict):

        flat = normalize_openai_usage(raw)

        details = _extract_details_from_mapping(raw)

        if not flat and not details:

            return None

        doc: UsageDocument = dict(flat or {})

        if details:

            doc["details"] = details

        return doc



    flat = _flat_usage_from_langchain_object(raw)

    doc: UsageDocument = dict(flat or {})



    usage_metadata = getattr(raw, "usage_metadata", None)

    if isinstance(usage_metadata, dict):

        meta_details = _extract_details_from_mapping(usage_metadata)

        if meta_details:

            doc["details"] = _merge_details(

                doc.get("details") if isinstance(doc.get("details"), dict) else None,

                meta_details,

            ) or meta_details



    response_metadata = getattr(raw, "response_metadata", None)

    if isinstance(response_metadata, dict):

        token_usage = response_metadata.get("token_usage")

        if isinstance(token_usage, dict):

            meta_details = _extract_details_from_mapping(token_usage)

            if meta_details:

                doc["details"] = _merge_details(

                    doc.get("details") if isinstance(doc.get("details"), dict) else None,

                    meta_details,

                ) or meta_details



    return doc if doc else None





def extract_usage_from_langchain_output(output: Any) -> OpenAIUsage | None:
    """Extract flat usage from ``on_chat_model_end`` output or an ``AIMessage``."""

    doc = extract_usage_document(output)
    if not doc:
        return None
    return usage_document_flat(doc) or None





def merge_openai_usage(base: OpenAIUsage | None, delta: OpenAIUsage | None) -> OpenAIUsage:

    """Sum two OpenAI-shaped usage dicts (missing keys treated as zero)."""



    merged: OpenAIUsage = dict(base or {})

    if not delta:

        return merged

    for key in _STANDARD_KEYS:

        if key not in delta:

            continue

        merged[key] = int(merged.get(key, 0)) + int(delta[key])

    return merged





def _merge_details(base: dict[str, Any] | None, delta: dict[str, Any] | None) -> dict[str, int] | None:

    """Sum numeric keys inside ``details``. Non-numeric values are skipped."""



    if not base and not delta:

        return None

    out: dict[str, int] = dict(base or {})

    for key, value in (delta or {}).items():

        n = _coerce_non_negative_int(value)

        if n is None:

            continue

        out[key] = int(out.get(key, 0)) + n

    return out or None





def _merge_usage_slice(base: UsageDocument | None, delta: UsageDocument | None) -> UsageDocument | None:

    """Merge one usage slice (standard keys + optional nested ``details``)."""



    if not base and not delta:

        return None

    merged: UsageDocument = dict(base or {})

    flat = merge_openai_usage(usage_document_flat(merged), usage_document_flat(delta or {}))

    merged.update(flat)

    details = _merge_details(

        merged.get("details") if isinstance(merged.get("details"), dict) else None,

        (delta or {}).get("details") if isinstance((delta or {}).get("details"), dict) else None,

    )

    if details:

        merged["details"] = details

    return merged or None





def merge_usage_document(base: UsageDocument | None, delta: UsageDocument | None) -> UsageDocument:

    """Merge layered usage documents (top-level, details, by_phase, by_step)."""



    if not base and not delta:

        return {}

    out: UsageDocument = dict(base or {})

    if not delta:

        return out



    flat_merged = merge_openai_usage(usage_document_flat(out), usage_document_flat(delta))

    out.update(flat_merged)



    details = _merge_details(

        out.get("details") if isinstance(out.get("details"), dict) else None,

        delta.get("details") if isinstance(delta.get("details"), dict) else None,

    )

    if details:

        out["details"] = details



    for bucket in ("by_phase", "by_step"):

        base_bucket = out.get(bucket) if isinstance(out.get(bucket), dict) else {}

        delta_bucket = delta.get(bucket) if isinstance(delta.get(bucket), dict) else {}

        merged_bucket: dict[str, Any] = dict(base_bucket)

        for name, slice_delta in delta_bucket.items():

            if not isinstance(slice_delta, dict):

                continue

            prev = merged_bucket.get(name) if isinstance(merged_bucket.get(name), dict) else {}

            merged_slice = _merge_usage_slice(prev, slice_delta) or {}

            if "skill_id" in slice_delta:

                merged_slice["skill_id"] = slice_delta["skill_id"]

            merged_bucket[name] = merged_slice

        if merged_bucket:

            out[bucket] = merged_bucket



    return out





def build_phase_delta(phase: str, usage: UsageDocument) -> UsageDocument:

    """Wrap one LLM call usage into a document increment keyed under ``by_phase``."""



    slice_doc = usage_document_for_node(usage)

    doc = dict(slice_doc)

    doc["by_phase"] = {phase: dict(slice_doc)}

    return doc





def build_step_delta(step_id: str, skill_id: str, usage: UsageDocument) -> UsageDocument:

    """Wrap top-level totals plus one ``by_step`` increment for persistence merge."""



    slice_doc = usage_document_for_node(usage)

    return {

        **dict(slice_doc),

        "by_step": {

            step_id: {

                **dict(slice_doc),

                "skill_id": skill_id,

            }

        },

    }


