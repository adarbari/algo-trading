"""The JSON Schema of the drafting model's answer and the local check against it (ADR 0041,
amended 2026-10-11). ``ANSWER_SCHEMA`` is the shape asked for today, ``{criteria, tie_break,
notes}``; a provider that supports structured output is sent it (``response_format`` /
``--json-schema``), and ``check_answer`` runs on every answer whatever the provider did, so a
provider that ignores the schema costs nothing but a repair. The schema is in the strict form
providers accept (every property listed in ``required``, an optional one nullable); the check
reads a missing nullable property as absent, so an answer that leaves out ``mode`` or ``why`` is
as valid as one with ``null``. It types the shape only: whether an op, mode or field is known
stays with ``criteria_of`` (a wrong one is dropped with a reason, not a rejected answer). A
later contract (several drafts, PR 5) extends this module's schema: a new answer key must be
nullable or optional (``["string", "null"]``), so answers recorded before it still pass. The
check is a small subset of JSON Schema (``type``, ``properties``, ``required``, ``items``,
``anyOf``), enough for these shapes and no dependency; a key the schema does not list is
tolerated (``additionalProperties = false`` is for the provider, strict mode needs it)."""

from collections.abc import Mapping
from typing import Any

SCALAR: tuple[Mapping[str, Any], ...] = (
    {"type": "string"},
    {"type": "number"},
    {"type": "boolean"},
)
NULLABLE_STRING: Mapping[str, Any] = {"type": ["string", "null"]}

CRITERION: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "id": NULLABLE_STRING,
        "field": {"type": "string"},
        "op": {"type": "string"},
        "value": {
            "anyOf": [
                *SCALAR,
                {"type": "array", "items": {"anyOf": list(SCALAR)}},
                {"type": "null"},
            ]
        },
        "mode": NULLABLE_STRING,
        "tolerance": {
            "anyOf": [
                {"type": "number"},
                {
                    "type": "object",
                    "properties": {"relative": {"type": "number"}},
                    "required": ["relative"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ]
        },
        "on_miss": NULLABLE_STRING,
        "why": NULLABLE_STRING,
    },
    "required": ["id", "field", "op", "value", "mode", "tolerance", "on_miss", "why"],
    "additionalProperties": False,
}
TIE_BREAK: Mapping[str, Any] = {
    "anyOf": [
        {
            "type": "object",
            "properties": {
                "field": {"type": "string"},
                "descending": {"type": ["boolean", "null"]},
            },
            "required": ["field", "descending"],
            "additionalProperties": False,
        },
        {"type": "null"},
    ]
}
ANSWER_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": CRITERION},
        "tie_break": TIE_BREAK,
        "notes": {"type": ["array", "null"], "items": {"type": "string"}},
    },
    "required": ["criteria", "tie_break", "notes"],
    "additionalProperties": False,
}

# What refuses a whole answer: a JSON object with a criteria list. Each criterion is checked
# on its own (``check_criterion``), so one malformed criterion is dropped with its reason, as
# before; tie_break and notes are read leniently.
ANSWER_SHAPE: Mapping[str, Any] = {
    "type": "object",
    "properties": {"criteria": {"type": "array"}},
    "required": ["criteria"],
}

_TYPES: Mapping[str, Any] = {
    "object": lambda v: isinstance(v, Mapping),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, int | float) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def check_answer(value: Any, schema: Mapping[str, Any] = ANSWER_SHAPE) -> str | None:
    """Why ``value`` does not fit ``schema`` (the first violation, with its path), else
    ``None``. By default the top-level shape only, which is what refuses an answer."""
    return _violation(value, schema, "answer")


def check_criterion(value: Any) -> str | None:
    """Why one proposed criterion does not fit ``CRITERION`` (it is dropped with this reason,
    the rest of the answer kept), else ``None``."""
    return _violation(value, CRITERION, "criterion")


def _violation(value: Any, schema: Mapping[str, Any], path: str) -> str | None:
    if "anyOf" in schema:
        if any(_violation(value, option, path) is None for option in schema["anyOf"]):
            return None
        return f"{path}: {_shown(value)} fits none of the allowed shapes"
    kinds = schema.get("type", ())
    kinds = [kinds] if isinstance(kinds, str) else list(kinds)
    if kinds and not any(_TYPES[k](value) for k in kinds):
        return f"{path}: expected {' or '.join(kinds)}, got {_shown(value)}"
    if isinstance(value, Mapping):
        return _object_violation(value, schema, path)
    if isinstance(value, list) and "items" in schema:
        for n, item in enumerate(value):
            if (why := _violation(item, schema["items"], f"{path}[{n}]")) is not None:
                return why
    return None


def _object_violation(value: Mapping[str, Any], schema: Mapping[str, Any], path: str) -> str | None:
    props: Mapping[str, Any] = schema.get("properties", {})
    for key in schema.get("required", ()):
        nullable = _allows_null(props.get(key, {}))
        if key not in value and not nullable:
            return f"{path}: missing {key!r}"
    for key, sub in props.items():
        if key in value and (why := _violation(value[key], sub, f"{path}.{key}")) is not None:
            return why
    return None


def _allows_null(schema: Mapping[str, Any]) -> bool:
    """A nullable property may be left out (an optional one in the strict form)."""
    kinds = schema.get("type", ())
    if "null" in ([kinds] if isinstance(kinds, str) else kinds):
        return True
    return any(_allows_null(option) for option in schema.get("anyOf", ()))


def _shown(value: Any) -> str:
    text = repr(value)
    return text if len(text) <= 60 else text[:57] + "..."
