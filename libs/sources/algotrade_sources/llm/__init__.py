"""The text-model adapter (ADR 0040): one OpenAI-compatible chat-completions client, which
any provider (Gemini, Groq, OpenRouter, Ollama, Anthropic's compatibility endpoint) answers by
``base_url`` alone. No vendor SDK; the transport is injected so tests never touch the network."""
