"""Accumulate assistant-channel streamed text for one agent run."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AssistantStreamCollector:
    """Buffer all ``llm.delta`` assistant fragments in memory until run finalize."""

    _parts: list[str] = field(default_factory=list)

    def append(self, text: str) -> None:
        """Append one streamed assistant fragment."""

        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        """Return the full concatenated assistant text for persistence."""

        return "".join(self._parts)

    def reset(self) -> None:
        """Clear buffered assistant text (before synthesizer replaces sub-agent narration)."""

        self._parts.clear()
