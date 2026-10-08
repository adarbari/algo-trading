"""Chat-completions response bodies of the two providers in the site chain, BUILT FROM THE
DOCUMENTATION, not recorded (no key existed when written): Anthropic's OpenAI-compatible
endpoint (``https://api.anthropic.com/v1/chat/completions``, ``usage.prompt_tokens`` and
``completion_tokens`` as the OpenAI SDK reads them) and Gemini's
(``.../v1beta/openai/chat/completions``, the same ``usage`` plus ``total_tokens``). Replace them
with bodies recorded on the first real call of each provider."""

import json


def anthropic_answer(text: str, prompt_tokens: int = 412, completion_tokens: int = 87) -> bytes:
    return json.dumps(
        {
            "id": "msg_01ABC",
            "object": "chat.completion",
            "model": "claude-haiku-4-5",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": "stop",
                    "message": {"role": "assistant", "content": text},
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    ).encode()


def gemini_answer(text: str, prompt_tokens: int = 398, completion_tokens: int = 2140) -> bytes:
    """``completion_tokens`` include the thinking tokens, as Gemini 3.x reports them."""
    return json.dumps(
        {
            "choices": [
                {
                    "finish_reason": "stop",
                    "index": 0,
                    "message": {"content": text, "role": "assistant"},
                }
            ],
            "created": 1760000000,
            "model": "gemini-2.5-flash",
            "object": "chat.completion",
            "usage": {
                "completion_tokens": completion_tokens,
                "prompt_tokens": prompt_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }
    ).encode()
