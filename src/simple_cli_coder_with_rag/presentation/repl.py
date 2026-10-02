"""Interactive REPL driven by a :class:`CommandRegistry`.

Lines starting with ``/`` dispatch to a registered command. Anything else
is a chat turn: the REPL hands the line to
:class:`~simple_cli_coder_with_rag.application.knowledge_service.KnowledgeService.chat`,
prints the model's reply, appends both the user turn and the assistant
turn to ``app_state.history``, and trims the history back to the configured
``history_cap`` (in turns) from the front when it grows past the limit.
"""

from __future__ import annotations

from collections.abc import Callable

from prompt_toolkit import PromptSession

from simple_cli_coder_with_rag.domain.llm_client import LLMError
from simple_cli_coder_with_rag.domain.messages import (
    AssistantMessage,
    UserMessage,
)
from simple_cli_coder_with_rag.presentation.commands import (
    AppState,
    CommandContext,
)
from simple_cli_coder_with_rag.presentation.registry import CommandRegistry


class Repl:
    """Block in a :mod:`prompt_toolkit` loop until a command exits."""

    _PROMPT = ">>> "

    def __init__(
        self,
        registry: CommandRegistry,
        app_state: AppState,
        *,
        output: Callable[[str], None] = print,
        on_exit: Callable[[], None] | None = None,
    ) -> None:
        self._registry = registry
        self._app_state = app_state
        self._output = output
        self._on_exit = on_exit
        self._should_exit = False

    def request_exit(self) -> None:
        """Set the flag that breaks the read-eval loop."""
        self._should_exit = True

    def run(self) -> None:
        """Read input, dispatch, repeat until :meth:`request_exit` is called.

        The optional ``on_exit`` callback (set in :meth:`__init__`) is
        invoked exactly once when the loop terminates — on a clean
        ``/exit``, on Ctrl-D, and after an unhandled exception bubbles
        out of :meth:`_handle`. The composition root uses it to call
        :meth:`~simple_cli_coder_with_rag.infrastructure.retrievers.executor.RetrievalExecutor.shutdown`
        so Ctrl-D does not hang waiting for in-flight retrieval
        (``docs/development-tools.md`` §9).
        """
        try:
            session: PromptSession[str] = PromptSession()
            while not self._should_exit:
                try:
                    line = session.prompt(self._PROMPT)
                except EOFError:
                    # Ctrl-D on an empty prompt: behave as /exit.
                    self._should_exit = True
                    break
                self._handle(line)
        finally:
            if self._on_exit is not None:
                self._on_exit()

    def _handle(self, line: str) -> None:
        """Dispatch a single line of input."""
        stripped = line.strip()
        if not stripped:
            return
        if not stripped.startswith("/"):
            self._handle_chat(stripped)
            return
        token = stripped[1:].split(maxsplit=1)[0]
        command = self._registry.get(token)
        if command is None:
            self._output(f"Unknown command: /{token}")
            self._output("Type /help for available commands.")
            return
        result = command.execute(CommandContext(repl=self, app_state=self._app_state))
        if result.message:
            self._output(result.message)

    def _handle_chat(self, line: str) -> None:
        """Route a chat line through the KnowledgeService and append to history.

        ``LLMError`` is caught here (and only here) so the rest of the code
        stays free of try/except ceremony. The error message is printed to
        stdout (not stderr — ``prompt_toolkit`` owns stderr) and the loop
        continues without polluting history.
        """
        knowledge = self._app_state.knowledge
        if knowledge is None:
            self._output("LLM not configured; type /help.")
            return
        try:
            # Snapshot the history: ``chat`` must see the turns that exist
            # *before* this message, and the captured call must remain stable
            # even after we append the new turn + assistant reply.
            response = knowledge.chat(line, history=list(self._app_state.history))
        except LLMError as exc:
            self._output(f"LLM error: {exc}")
            return
        self._output(response)
        self._app_state.history.append(UserMessage(content=line))
        self._app_state.history.append(AssistantMessage(content=response))
        # Trim from the front so we keep at most ``history_cap`` turns.
        cap = 2 * self._app_state.history_cap
        if len(self._app_state.history) > cap:
            self._app_state.history[:] = self._app_state.history[-cap:]


__all__ = ["Repl"]
