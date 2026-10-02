"""``/provider <id>`` — switch the active provider mid-session."""

from __future__ import annotations

from simple_cli_coder_with_rag.infrastructure.llm import build_llm_client
from simple_cli_coder_with_rag.infrastructure.providers import UnknownProviderError
from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)


class ProviderCommand:
    """``/provider <id>``: set active provider and rebuild the LLM adapter."""

    name = "provider"
    summary = "Switch the active provider."

    def execute(self, context: CommandContext) -> CommandResult:
        registry = context.app_state.provider_registry
        if registry is None:
            return CommandResult(message="provider registry not configured")
        provider_id = context.args.strip().split()[0] if context.args.strip() else ""
        if not provider_id:
            return CommandResult(message="usage: /provider <id>")
        try:
            registry.set_active(provider_id)
        except UnknownProviderError:
            return CommandResult(message=f"unknown provider '{provider_id}'")

        config = registry.get(provider_id)
        client = build_llm_client(config)
        context.app_state.llm = client
        if context.app_state.knowledge is not None:
            context.app_state.knowledge.set_llm(client)
            context.app_state.knowledge.set_model(config.default_model, config.default_model)

        message = f"active provider: {provider_id}"
        if not config.api_key.get_secret_value():
            message += (
                f"\nwarning: {provider_id} has no API key yet. "
                f"Run `/connect {provider_id}` to add one."
            )
        return CommandResult(message=message)


__all__ = ["ProviderCommand"]
