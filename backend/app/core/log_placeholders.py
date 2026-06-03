"""SLF4J-style {} placeholder formatting for Minerva log messages."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging_text import format_log_value


@dataclass(frozen=True)
class PlaceholderResult:
    """Outcome of formatting one log message template."""

    message: str
    matched: bool
    expected: int
    provided: int


def format_placeholders(template: str, *args: object) -> PlaceholderResult:
    """Replace unescaped `{}` placeholders with formatted argument values."""

    parts: list[str] = []
    arg_index = 0
    placeholder_count = 0
    index = 0
    while index < len(template):
        if template.startswith("{{", index):
            parts.append("{")
            index += 2
            continue
        if template.startswith("}}", index):
            parts.append("}")
            index += 2
            continue
        if template.startswith("{}", index):
            placeholder_count += 1
            if arg_index >= len(args):
                return PlaceholderResult(
                    message=template,
                    matched=False,
                    expected=placeholder_count,
                    provided=len(args),
                )
            parts.append(format_log_value(args[arg_index]))
            arg_index += 1
            index += 2
            continue
        parts.append(template[index])
        index += 1

    if placeholder_count != len(args):
        return PlaceholderResult(
            message=template,
            matched=False,
            expected=placeholder_count,
            provided=len(args),
        )
    return PlaceholderResult(
        message="".join(parts),
        matched=True,
        expected=placeholder_count,
        provided=len(args),
    )
