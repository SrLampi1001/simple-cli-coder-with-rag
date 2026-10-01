"""Project-owned ``LLMClient`` Protocol and ``LLMError``.

The Adapter pattern (``README.md`` *Adapter*): every concrete implementation
lives in ``infrastructure/llm/`` and translates the vendor's wire format
into our ``Message`` / ``ToolSpec`` / ``AssistantTurn`` shape. The application
and presentation layers only ever see this Protocol, so a vendor type cannot
leak upward.
"""

from __future__ import annotations

from typing import Protocol

from simple_cli_coder_with_rag.domain.messages import (
    AssistantTurn,
    Message,
    ToolSpec,
)


class LLMClient(Protocol):
    """The single seam the application layer knows about.

    ``complete`` returns the model's text reply for a plain chat turn.
    ``complete_with_tools`` is the same call shape plus a list of tool
    definitions; in DO-02 the adapters implement it as a stub that returns
    an empty ``tool_calls`` list (DO-10 fills it in).
    """

    def complete(self, messages: list[Message], *, model: str) -> str: ...

    def complete_with_tools(
        self,
        messages: list[Message],
        *,
        model: str,
        tools: list[ToolSpec],
    ) -> AssistantTurn: ...


class LLMError(Exception):
    """Raised by every concrete adapter when the vendor layer fails.

    Vendor-specific exceptions (``anthropic.APIError``, ``urllib.error.URLError``
    …) are wrapped here at the adapter boundary so the rest of the codebase
    only needs to catch ``LLMError``.
    """


__all__ = ["LLMClient", "LLMError"]
