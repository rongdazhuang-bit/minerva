"""Text cleaning rules aligned with Dify ``CleanProcessor``."""

from __future__ import annotations

import re
from typing import Any


def clean_text(text: str, process_rule: dict[str, Any] | None) -> str:
    """Apply pre-processing rules from a dataset process rule payload."""

    text = re.sub(r"<\|", "<", text)
    text = re.sub(r"\|>", ">", text)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\xEF\xBF\xBE]", "", text)
    text = re.sub("\ufffe", "", text)

    rules = (process_rule or {}).get("rules") or process_rule or {}
    if not isinstance(rules, dict):
        return text
    pre_rules = rules.get("pre_processing_rules") or []
    for rule in pre_rules:
        if not rule.get("enabled"):
            continue
        rid = rule.get("id")
        if rid == "remove_extra_spaces":
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(
                r"[\t\f\r\x20\u00a0\u1680\u180e\u2000-\u200a\u202f\u205f\u3000]{2,}",
                " ",
                text,
            )
        elif rid == "remove_urls_emails":
            text = re.sub(r"([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)", "", text)
            markdown_image_pattern = r"!\[.*?\]\((https?://[^\s)]+)\)"
            placeholders: list[str] = []

            def _replace(match: re.Match[str]) -> str:
                url = match.group(1)
                placeholder = f"__MARKDOWN_IMAGE_URL_{len(placeholders)}__"
                placeholders.append(url)
                return f"![image]({placeholder})"

            text = re.sub(markdown_image_pattern, _replace, text)
            text = re.sub(r"https?://[^\s)]+", "", text)
            for i, url in enumerate(placeholders):
                text = text.replace(f"__MARKDOWN_IMAGE_URL_{i}__", url)
    return text.strip()
