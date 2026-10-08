"""The text-model adapter (ADR 0041): one OpenAI-compatible chat-completions client, which
any provider (Gemini, Groq, OpenRouter, Ollama, Anthropic's compatibility endpoint) answers by
``base_url`` alone, and ``claude_cli``: Claude Code run headless under the owner's own login
(ADR 0041, amended 2026-10-08). No vendor SDK; the transport is injected so tests never touch
the network."""
