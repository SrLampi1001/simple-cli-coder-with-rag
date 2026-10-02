"""``/providers`` — list configured providers and the active one."""

from __future__ import annotations

from simple_cli_coder_with_rag.presentation.commands import (
    CommandContext,
    CommandResult,
)


class ProvidersCommand:
    """``/providers``: sorted table of every registry entry."""

    name = "providers"
    summary = "List configured providers and the active one."

    def execute(self, context: CommandContext) -> CommandResult:
        registry = context.app_state.provider_registry
        if registry is None:
            return CommandResult(message="provider registry not configured")
        lines = []
        for provider_id, config in registry.list():
            key_set = "yes" if config.api_key.get_secret_value() else "no"
            lines.append(
                f"{provider_id}  {config.adapter}  {config.base_url}  "
                f"{config.default_model}  {key_set}"
            )
        active = registry.active_provider_id or "none"
        lines.append(f"active: {active}")
        return CommandResult(message="\n".join(lines))


__all__ = ["ProvidersCommand"]
