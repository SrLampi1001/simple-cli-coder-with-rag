# Supported providers

Provider credentials and per-provider defaults live in the JSON registry at
`~/.local/share/simple-cli-coder-with-rag/providers.json` (gitignored). The
file is created on first run with the five providers below pre-populated —
API keys start empty. Use `/connect <id>` in the REPL to add a key,
`/providers` to list entries, and `/provider <id>` to activate one.

| id          | adapter     | base_url                                | default_model              | context_window | Where to get a key                                                |
|-------------|-------------|-----------------------------------------|----------------------------|----------------|-------------------------------------------------------------------|
| `nvidia`    | `openai`    | `https://integrate.api.nvidia.com/v1`   | `openai/gpt-oss-20b`       | 128000         | https://build.nvidia.com/ (NVIDIA NIM)                            |
| `mistral`   | `openai`    | `https://api.mistral.ai/v1`             | `mistral-code-latest`      | 128000         | https://console.mistral.ai/                                       |
| `minimax`   | `anthropic` | `https://api.minimax.io/anthropic`      | `MiniMax-M3`               | 128000         | https://platform.minimaxi.com/ (MiniMax, Anthropic-compatible)    |
| `anthropic` | `anthropic` | `https://api.anthropic.com`             | `claude-3-5-sonnet-latest` | 200000         | https://console.anthropic.com/                                    |
| `openai`    | `openai`    | `https://api.openai.com/v1`             | `gpt-4o-mini`              | 128000         | https://platform.openai.com/api-keys                              |

Custom OpenAI-compatible or Anthropic-compatible endpoints can be added with:

```
/connect --new <id> --adapter <openai|anthropic> --base-url <https-url> --model <model>
```

Both adapters use the official vendor SDKs (`openai`, `anthropic`); adapter
selection is driven by each entry's `adapter` field.
