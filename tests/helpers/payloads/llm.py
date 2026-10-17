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


def claude_cli_structured(structured: object, result: str = "") -> str:
    """``claude -p --output-format json --json-schema ...`` stdout, RECORDED 2026-10-11 (claude
    2.1.295, model haiku, the lockdown flags incl. ``--tools ""``, schema ``{n, a (string or
    null), b}``): the CLI answers in ``structured_output`` and also repeats it as a string in
    ``result``. Ids, durations and paths are removed; ``structured`` and ``result`` are the
    only parts a test varies."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "is_error": False,
            "stop_reason": "tool_use",
            "num_turns": 2,
            "result": result,
            "structured_output": structured,
            "usage": {
                "input_tokens": 2,
                "cache_creation_input_tokens": 1395,
                "cache_read_input_tokens": 0,
                "output_tokens": 93,
            },
            "total_cost_usd": 0.0003257,
            "permission_denials": [],
            "terminal_reason": "completed",
        }
    )


RECORDED_STRUCTURED = claude_cli_structured(
    {"n": 1, "a": None, "b": False}, '{"n":1,"a":null,"b":false}'
)

QUOTA_MESSAGE = "You exceeded your current quota, please check your plan and billing details."


def _google_quota(quota_id: str, retry: str | None = None) -> bytes:
    details: list[dict[str, object]] = [
        {
            "@type": "type.googleapis.com/google.rpc.QuotaFailure",
            "violations": [
                {"quotaMetric": "generativelanguage.googleapis.com/x", "quotaId": quota_id}
            ],
        }
    ]
    if retry:
        details.append({"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": retry})
    return json.dumps(
        [
            {
                "error": {
                    "code": 429,
                    "message": QUOTA_MESSAGE,
                    "status": "RESOURCE_EXHAUSTED",
                    "details": details,
                }
            }
        ]
    ).encode()


# Shaped after Gemini's 429 bodies as seen in usage/llm_calls 2026-10-17 (not byte-recorded).
GEMINI_QUOTA_PER_DAY = _google_quota("GenerateRequestsPerDayPerProjectPerModel-FreeTier")
GEMINI_QUOTA_PER_MINUTE = _google_quota(
    "GenerateRequestsPerMinutePerProjectPerModel-FreeTier", "34s"
)
OPENAI_INSUFFICIENT_QUOTA = json.dumps(
    {
        "error": {
            "message": QUOTA_MESSAGE,
            "type": "insufficient_quota",
            "code": "insufficient_quota",
        }
    }
).encode()
