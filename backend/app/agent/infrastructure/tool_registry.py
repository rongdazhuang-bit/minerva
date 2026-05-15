"""Register OpenAI-style function tools and invoke them by name."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

JsonHandler = Callable[..., Awaitable[Any]]


class ToolRegistry:
    """Maps tool name to JSON Schema plus async handler; builds OpenAI ``tools`` payload."""

    def __init__(self) -> None:
        self._entries: dict[str, tuple[dict[str, Any], JsonHandler]] = {}

    def register(
        self,
        name: str,
        handler: JsonHandler,
        *,
        description: str,
        parameters: dict[str, Any],
    ) -> None:
        """Register a callable tool under a unique ``name`` with JSON Schema ``parameters``."""

        self._entries[name] = (
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": description,
                    "parameters": parameters,
                },
            },
            handler,
        )

    def get_openai_tools_payload(self) -> list[dict[str, Any]]:
        """Return the ``tools=[...]`` array for chat completions."""

        return [tpl[0] for tpl in self._entries.values()]

    def has_tool(self, name: str) -> bool:
        """Return whether ``name`` is registered."""

        return name in self._entries

    async def invoke(self, name: str, arguments_json: str) -> str:
        """Parse JSON arguments and await the handler; stringifies non-str results."""

        if name not in self._entries:
            raise KeyError(name)
        _spec, handler = self._entries[name]
        try:
            args = json.loads(arguments_json or "{}")
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid tool arguments JSON: {e}") from e
        if not isinstance(args, dict):
            raise TypeError("tool arguments must be a JSON object")
        result = await handler(**args)
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False)
