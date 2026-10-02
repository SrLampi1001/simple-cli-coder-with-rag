"""Interactive REPL driven by a :class:`CommandRegistry`.

Lines starting with ``/`` dispatch to a registered command. Anything else
is a chat turn: the REPL hands the line to
:class:`~simple_cli_coder_with_rag.application.knowledge_service.KnowledgeService.chat`,
prints the model's reply, appends both the user turn and the assistant
turn to ``app_state.history``, and trims the history back to the
configured window from the front when it grows past the limit. The cap
is read from ``app_state.settings.int_history_cap`` (default
``10`` turns = ``20`` messages) — DO-12 lifted the cap from a hard-coded
``history_cap=20`` to a configurable value matching the spec "10 most
recent user/assistant messages".

Persistence (DO-12):

* After every successful chat turn, the REPL appends the user turn
  and the assistant reply to ``<session_id>.jsonl`` via
  ``SessionStore.append``. A ``seen`` set built from
  ``SessionStore.read(session_id)`` at the start of each turn drops
  already-persisted messages so a resumed session whose transcript
  is already on disk never re-appends lines.

Recall integration (DO-09):

* Before every chat turn the REPL calls ``knowledge.recall(input)`` —
  the coordinator's :class:`TrivialGate` short-circuits on short
  prompts, so this is free for trivial input.
* The returned ``list[str]`` is forwarded to ``knowledge.chat(...)`` as
  the ``recalled`` kwarg; :func:`build_chat_messages` injects them as
  a ``SystemMessage`` at the head of the LLM request.
* ``recall`` failures are caught here as a defensive last-resort so a
  novel exception cannot bring down the chat loop. The coordinator
  already handles the documented failure paths
  (``EmbedderNotReady``, ``TimeoutError``, generic ``RuntimeError``);
  this catch only triggers for an unrelated bug.
"""

from __future__ import annotations

from collections.abc import Callable

from loguru import logger
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

# DO-12 fallback cap when ``app_state.settings`` is ``None`` (legacy unit
# tests that build a bare ``AppState()``). The documented default is
# ``10`` turns = ``20`` messages, matching the TL acceptance criterion
# "10 most recent user/assistant messages".
_DEFAULT_HISTORY_CAP_TURNS = 10


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
        parts = stripped[1:].split(maxsplit=1)
        token = parts[0]
        rest = parts[1] if len(parts) > 1 else ""
        command = self._registry.get(token)
        if command is None:
            self._output(f"Unknown command: /{token}")
            self._output("Type /help for available commands.")
            return
        result = command.execute(CommandContext(repl=self, app_state=self._app_state, args=rest))
        if result.message:
            self._output(result.message)

    def _handle_chat(self, line: str) -> None:
        """Route a chat line through the KnowledgeService and append to history.

        ``LLMError`` is caught here (and only here) so the rest of the code
        stays free of try/except ceremony. The error message is printed to
        stdout (not stderr — ``prompt_toolkit`` owns stderr) and the loop
        continues without polluting history.

        Recall (DO-09): ``knowledge.recall(line)`` runs first; the
        coordinator handles the trivial-prompt short-circuit, the
        similarity threshold, and the documented failure paths. A
        residual ``except Exception`` here is defensive only — it
        guarantees the chat loop survives an unexpected vendor bug.

        Persistence (DO-12): every successful turn is appended to the
        on-disk ``<session_id>.jsonl`` transcript. We persist the
        messages this turn added — the ``persisted_through`` counter on
        :class:`AppState` tracks which messages in ``history`` have
        already been persisted, so ``/resume <id>`` followed by typing
        never duplicates lines (the loaded messages have their
        ``persisted_through`` index advanced by ``ResumeCommand``).

        Trim (DO-12): the active history is trimmed to the last
        ``2 * int_history_cap`` messages (= the last
        ``int_history_cap`` user/assistant turns) once the turn
        finishes. The on-disk transcript is *not* trimmed — the full
        history stays for ``/chats`` / ``/resume <id>``.
        """
        knowledge = self._app_state.knowledge
        if knowledge is None:
            self._output("LLM not configured; type /help.")
            return
        # Resolve the cap once per turn so a Settings edit mid-run
        # would still need a restart (consistent with the rest of the
        # composition root, which builds Settings at boot only).
        capacity = self._resolve_history_cap()
        # Persistence pre-flight: ensure the session has a stable id
        # before we touch disk, so a /resume later can find the
        # transcript by id. ``session_store is None`` (legacy tests)
        # short-circuits the persistence step below.
        store = self._app_state.session_store
        if store is not None and not self._app_state.session_id:
            self._app_state.session_id = store.current_id()
        # Recall runs before chat. The coordinator already catches the
        # documented failure paths; this outer try/except is a defensive
        # last resort so a novel exception cannot kill the chat loop.
        try:
            recalled = knowledge.recall(line)
        except Exception as exc:
            logger.debug("recall failed unexpectedly: {}", exc)
            recalled = []
        try:
            # Snapshot the history: ``chat`` must see the turns that exist
            # *before* this message, and the captured call must remain stable
            # even after we append the new turn + assistant reply.
            response = knowledge.chat(
                line, history=list(self._app_state.history), recalled=recalled
            )
        except LLMError as exc:
            self._output(f"LLM error: {exc}")
            return
        self._output(response)
        user_msg = UserMessage(content=line)
        assistant_msg = AssistantMessage(content=response)
        self._app_state.history.append(user_msg)
        self._app_state.history.append(assistant_msg)
        # Persist the messages this turn added. ``persisted_through``
        # is the count of messages already on disk; we only append
        # what is new since ``persisted_through`` was last updated.
        # ``ResumeCommand`` advances ``persisted_through`` so the
        # messages loaded from disk are never re-appended.
        if store is not None:
            for msg in self._app_state.history[self._app_state.persisted_through :]:
                store.append(self._app_state.session_id, msg)
        self._app_state.persisted_through = len(self._app_state.history)
        # Trim from the front so we keep at most ``int_history_cap``
        # turns (= 2 * capacity messages). Drop the oldest messages
        # when the history grew past the cap.
        if len(self._app_state.history) > capacity:
            self._app_state.history[:] = self._app_state.history[-capacity:]

    def _resolve_history_cap(self) -> int:
        """Return the in-memory history cap (in messages) for this turn.

        Reads ``Settings.int_history_cap`` (in *turns*; one turn = two
        messages) from ``app_state.settings``. Falls back to
        ``_DEFAULT_HISTORY_CAP_TURNS`` (= ``10``) when ``settings`` is
        ``None`` so legacy unit tests that build a bare ``AppState``
        keep passing.
        """
        settings = self._app_state.settings
        cap_turns = settings.int_history_cap if settings is not None else _DEFAULT_HISTORY_CAP_TURNS
        return 2 * cap_turns


__all__ = ["Repl"]
