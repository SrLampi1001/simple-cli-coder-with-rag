"""``/connect`` — add an API key for a provider (OpenCode UX).

``/connect <id>`` prompts for the key (getpass, no echo), validates it with
a one-shot ``complete(...)`` ping, and writes it back to ``providers.json``
via :meth:`ProviderRegistry.upsert`. ``--no-validate`` skips the round-trip.
``/connect --new <id> --adapter <a> --base-url <u> --model <m>`` registers a
custom provider with the same flow.
"""

from __future__ import annotations

import argparse
import getpass
import shlex

from pydantic import SecretStr, ValidationError

from simple_cli_coder_with_rag.domain.messages import SystemMessage, UserMessage
from simple_cli_coder_with_rag.infrastructure.llm import build_llm_client
from simple_cli_coder_with_rag.infrastructure.providers import (
    ProviderConfig,
    UnknownProviderError,
)
from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)

_KNOWN_ADAPTERS = ("openai", "anthropic")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="/connect")
    parser.add_argument("id", nargs="?", default=None)
    parser.add_argument("--new", action="store_true", dest="new")
    parser.add_argument("--adapter", default=None)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--no-validate", action="store_true", dest="no_validate")
    return parser


class ConnectCommand:
    """``/connect``: prompt for and persist a provider API key."""

    name = "connect"
    summary = "Add an API key for a provider (prompts securely)."

    def execute(self, context: CommandContext) -> CommandResult:
        registry = context.app_state.provider_registry
        if registry is None:
            return CommandResult(message="connect failed: provider registry not configured")

        try:
            ns = _build_parser().parse_args(shlex.split(context.args))
        except SystemExit:
            return CommandResult(
                message=(
                    "usage: /connect <id> | /connect --new <id> --adapter <a> "
                    "--base-url <u> --model <m> [--no-validate]"
                )
            )

        try:
            if ns.new:
                config = self._new_config(ns)
                provider_id = ns.id
                if provider_id is None:
                    return CommandResult(message="connect failed: --new requires a provider id")
            else:
                if ns.id is None:
                    return CommandResult(message="usage: /connect <id> [--no-validate]")
                provider_id = ns.id
                try:
                    config = registry.get(provider_id)
                except UnknownProviderError:
                    return CommandResult(
                        message=(
                            f"unknown provider '{provider_id}'. "
                            "Run /providers to see what's available."
                        )
                    )
        except _RejectedError as exc:
            return CommandResult(message=str(exc))

        key = getpass.getpass(f"API key for {provider_id}: ").strip()
        if not key:
            return CommandResult(message=f"connect aborted: empty API key for '{provider_id}'")

        candidate = config.model_copy(update={"api_key": SecretStr(key)})
        if not ns.no_validate:
            try:
                client = build_llm_client(candidate)
                reply = client.complete(
                    messages=[
                        SystemMessage(content="ping"),
                        UserMessage(content="ping"),
                    ],
                    model=candidate.default_model,
                )
            except Exception as exc:
                return CommandResult(message=f"API key validation failed for {provider_id}: {exc}")
            if not reply or not reply.strip():
                return CommandResult(
                    message=f"API key validation failed for {provider_id}: empty response"
                )

        registry.upsert(provider_id, candidate)
        if ns.no_validate:
            return CommandResult(
                message=(
                    f"connected {provider_id} (no validation; "
                    f"adapter={candidate.adapter}, model={candidate.default_model})"
                )
            )
        return CommandResult(
            message=(
                f"connected {provider_id} (adapter={candidate.adapter}, "
                f"model={candidate.default_model})"
            )
        )

    def _new_config(self, ns: argparse.Namespace) -> ProviderConfig:
        if ns.adapter not in _KNOWN_ADAPTERS:
            raise _RejectedError(
                f"unknown adapter '{ns.adapter}'. Expected one of: {', '.join(_KNOWN_ADAPTERS)}."
            )
        if ns.base_url is None or not ns.base_url.startswith("https://"):
            raise _RejectedError("invalid --base-url: must start with 'https://'")
        if not ns.model or not ns.model.strip():
            raise _RejectedError("invalid --model: must be non-empty")
        try:
            return ProviderConfig(
                adapter=ns.adapter,  # type: ignore[arg-type]
                base_url=ns.base_url,
                default_model=ns.model,
            )
        except ValidationError as exc:
            raise _RejectedError(f"invalid provider config: {exc}") from exc


class _RejectedError(Exception):
    pass


__all__ = ["ConnectCommand"]
