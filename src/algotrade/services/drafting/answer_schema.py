"""The JSON Schema of the drafting model's answer and the local check against it (ADR 0041,
amended 2026-10-11). ``ANSWER_SCHEMA`` is the shape asked for today, ``{criteria, tie_break,
notes}``; a provider that supports structured output is sent it (``response_format`` /
``--json-schema``), and ``check_answer`` runs on every answer whatever the provider did, so a
provider that ignores the schema costs nothing but a repair. The schema is in the strict form
providers accept (every property listed in ``required``, an optional one nullable); the check
reads a missing nullable property as absent, so an answer that leaves out ``mode`` or ``why`` is
as valid as one with ``null``. It types the shape only: whether an op, mode or field is known
stays with ``criteria_of`` (a wrong one is dropped with a reason, not a rejected answer). The
A / B / C contract (PR 5, ADR 0041 amendment 2026-10-11) adds ``formulas`` (B1), ``missing``
(B2 / C) and ``unresolved`` (an ambiguous term with ready alternatives); every one is nullable
or optional, so answers recorded before it still pass (a new answer key must be the same). The
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
STRINGS: Mapping[str, Any] = {"type": "array", "items": {"type": "string"}}
FORMULA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "expr": {"type": "string"},
        "dtype": {"type": "string"},
        "unit": {"type": "string"},
        "description": {"type": "string"},
        "null_meaning": {"type": "string"},
        "inputs": STRINGS,
        "criterion": {
            "anyOf": [
                {
                    "type": "object",
                    "properties": {
                        key: CRITERION["properties"][key]
                        for key in ("op", "value", "mode", "tolerance")
                    },
                    "required": ["op", "value", "mode", "tolerance"],
                    "additionalProperties": False,
                },
                {"type": "null"},
            ]
        },
    },
    "required": [
        "name", "expr", "dtype", "unit", "description", "null_meaning", "inputs", "criterion",
    ],
    "additionalProperties": False,
}  # fmt: skip
MISSING: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "key": NULLABLE_STRING,
        "new_key_slug": NULLABLE_STRING,
        "span": {"type": "string"},
        "description": {"type": "string"},
        "why_needed": {"type": "string"},
        "closest": STRINGS,
        "feasibility": {"type": "string"},
    },
    "required": [
        "key", "new_key_slug", "span", "description", "why_needed", "closest", "feasibility",
    ],
    "additionalProperties": False,
}  # fmt: skip
UNRESOLVED: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "term": {"type": "string"},
        "span": {"type": "string"},
        "default_index": {"type": "integer"},
        "alternatives": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"label": {"type": "string"}, "criterion": CRITERION},
                "required": ["label", "criterion"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["term", "span", "default_index", "alternatives"],
    "additionalProperties": False,
}
ANSWER_SCHEMA: Mapping[str, Any] = {
    "type": "object",
    "properties": {
        "criteria": {"type": "array", "items": CRITERION},
        "tie_break": TIE_BREAK,
        "notes": {"type": ["array", "null"], "items": {"type": "string"}},
        "formulas": {"type": ["array", "null"], "items": FORMULA},
        "missing": {"type": ["array", "null"], "items": MISSING},
        "unresolved": {"type": ["array", "null"], "items": UNRESOLVED},
    },
    "required": ["criteria", "tie_break", "notes", "formulas", "missing", "unresolved"],
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
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
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


def check_item(value: Any, schema: Mapping[str, Any], name: str) -> str | None:
    """Why one proposed formula / missing / unresolved item (``FORMULA``, ``MISSING``,
    ``UNRESOLVED``) does not fit its schema (it is dropped with this reason), else ``None``."""
    return _violation(value, schema, name)


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
