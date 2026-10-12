"""A phrasebook entry's structured threshold (``[[phrase.criterion]]`` and
``[[phrase.alternative]]`` in ``config/site/phrasebook.toml``), typed and checked as far as the
file alone allows: a field name, a known op, a value of the shape the op takes, a mode,
a tolerance only where the mode
uses one, an ``on_miss`` only on a soft criterion. It is the same shape as one criterion of the
drafting answer (``services/drafting/answer_schema.CRITERION``: ``field``, ``op``, ``value``,
``mode``, ``tolerance``, ``on_miss``), so ``as_answer`` turns it into that dict. Whether the
field is in the site catalogue and the op fits its type is checked against the catalogue by
``services/drafting/phrasebook`` (the loader has no catalogue)."""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table, unique
from algotrade.core.model.errors import ConfigurationError
from algotrade.core.model.predicates import NO_VALUE_OPS, NUMERIC_OPS, OPS

MODES = ("hard", "soft", "score")
MISSES = ("WATCH", "LIQUIDITY_RISK", "EVENT_RISK")
CRITERION_KEYS = ("field", "op", "value", "mode", "tolerance", "on_miss")
ALTERNATIVE_KEYS = ("label", *CRITERION_KEYS)
PHRASE_THRESHOLD_KEYS = ("criterion", "alternative", "default")
_LABEL = re.compile(r"^[^\s].{0,38}[^\s]$|^[^\s]$")

type Scalar = str | int | float | bool
type Tolerance = float | tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class PhraseCriterion:
    """One criterion of a phrase: ``field`` / ``op`` / ``value`` (a list for ``in``, ``not_in``
    and ``between``; ``None`` for ``is_null`` / ``not_null``), the ``mode`` (``hard`` gates;
    ``soft`` and ``score`` rank), the ``tolerance`` (a number, or ``(("relative", x),)``) and
    ``on_miss`` of a soft one."""

    field: str
    op: str
    value: Scalar | tuple[Scalar, ...] | None = None
    mode: str = "hard"
    tolerance: Tolerance | None = None
    on_miss: str | None = None

    def short(self) -> str:
        """``field op value`` as the prompt shows it (the field's column, mode when not hard)."""
        column = self.field.rsplit(".", 1)[-1]
        shown = "" if self.op in NO_VALUE_OPS else f" {_show(self.value)}"
        text = f"{column} {self.op}{shown}"
        if self.mode == "hard":
            return text
        extra = ""
        if self.tolerance is not None:
            extra = f" tol {_show(self.tolerance)}"
        return f"{text} {self.mode}{extra}"

    def as_answer(self) -> dict[str, Any]:
        """The criterion as the drafting answer carries it (``CRITERION`` of ``answer_schema``)."""
        out: dict[str, Any] = {"field": self.field, "op": self.op}
        if self.op not in NO_VALUE_OPS:
            out["value"] = list(self.value) if isinstance(self.value, tuple) else self.value
        out["mode"] = self.mode
        if self.tolerance is not None:
            out["tolerance"] = (
                dict(self.tolerance) if isinstance(self.tolerance, tuple) else self.tolerance
            )
        if self.on_miss:
            out["on_miss"] = self.on_miss
        return out


@dataclass(frozen=True)
class PhraseAlternative:
    """One reading of an ambiguous word ("liquid": 10M, 50M or 100M a day): a ``label`` the
    trader sees and the criterion it stands for (the shape of an ``unresolved`` alternative)."""

    label: str
    criterion: PhraseCriterion


def _show(value: Any) -> str:
    if isinstance(value, tuple) and value and isinstance(value[0], tuple):
        return "+".join(f"{k} {v:g}" for k, v in value)  # a relative tolerance
    if isinstance(value, tuple):
        return "[" + ",".join(_show(v) for v in value) + "]"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def _number(v: Any) -> bool:
    return isinstance(v, int | float) and not isinstance(v, bool)


def _scalar(v: Any) -> bool:
    return isinstance(v, str | int | float | bool)


def _value(t: Table, op: str) -> Scalar | tuple[Scalar, ...] | None:
    raw = t.raw("value")
    if op in NO_VALUE_OPS:
        if raw is not None:
            raise ConfigurationError(f"{t.where} value: {op} takes no value")
        return None
    if raw is None:
        raise ConfigurationError(f"{t.where} value: {op} needs a value")
    if op in ("in", "not_in"):
        if not isinstance(raw, list) or not raw or not all(_scalar(v) for v in raw):
            raise ConfigurationError(f"{t.where} value: {op} takes a non-empty list, got {raw!r}")
        return tuple(raw)
    if op == "between":
        if not isinstance(raw, list) or len(raw) != 2 or not all(_number(v) for v in raw):
            raise ConfigurationError(f"{t.where} value: between takes two numbers, got {raw!r}")
        if raw[0] > raw[1]:
            raise ConfigurationError(f"{t.where} value: between needs low <= high, got {raw!r}")
        return tuple(raw)
    if op in NUMERIC_OPS:
        if not _number(raw):
            raise ConfigurationError(f"{t.where} value: {op} takes a number, got {raw!r}")
        return raw  # type: ignore[no-any-return]
    if not _scalar(raw):  # eq / ne
        raise ConfigurationError(f"{t.where} value: {op} takes one number, text or boolean")
    return raw  # type: ignore[no-any-return]


def _tolerance(t: Table) -> Tolerance | None:
    raw = t.raw("tolerance")
    if raw is None:
        return None
    if _number(raw) and raw >= 0:
        return float(raw)
    if (
        isinstance(raw, Mapping)
        and set(raw) == {"relative"}
        and _number(raw["relative"])
        and raw["relative"] >= 0
    ):
        return (("relative", float(raw["relative"])),)
    raise ConfigurationError(f"{t.where} tolerance: expected a number >= 0 or {{relative = x}}")


def parse_criterion(t: Table, keys: tuple[str, ...] = CRITERION_KEYS) -> PhraseCriterion:
    """One criterion table; the error names the file, entry and key."""
    t.only(keys)
    field_name = t.text("field", "")
    if not field_name:
        raise ConfigurationError(f"{t.where} field: expected a catalogue field name")
    op = t.text("op", "")
    if op not in OPS:
        raise ConfigurationError(f"{t.where} op: expected one of {sorted(OPS)}, got {op!r}")
    mode = t.choice("mode", "hard", MODES)
    tolerance = _tolerance(t)
    on_miss = t.raw("on_miss")
    if tolerance is not None and mode == "hard":
        raise ConfigurationError(f"{t.where} tolerance: a hard criterion has none")
    if on_miss is not None and (mode != "soft" or on_miss not in MISSES):
        raise ConfigurationError(f"{t.where} on_miss: a soft criterion only, one of {MISSES}")
    return PhraseCriterion(field_name, op, _value(t, op), mode, tolerance, on_miss)


def parse_threshold(
    t: Table,
) -> tuple[tuple[PhraseCriterion, ...], tuple[PhraseAlternative, ...], int]:
    """A phrase's ``criterion`` tables (the exact reading) or its ``alternative`` tables (a
    word with several readings, ``default`` the label the draft starts with); both together
    are refused. Returns ``(criteria, alternatives, default_index)``."""
    criteria = tuple(parse_criterion(c) for c in t.tables("criterion"))
    tables = t.tables("alternative")
    if criteria and tables:
        raise ConfigurationError(f"{t.where}: criterion and alternative are exclusive")
    if not tables:
        if t.raw("default") is not None:
            raise ConfigurationError(f"{t.where} default: only with alternatives")
        return criteria, (), 0
    alternatives = []
    for a in tables:
        label = a.text("label", "")
        if not _LABEL.match(label):
            raise ConfigurationError(f"{a.where} label: expected a short non-empty label")
        alternatives.append(PhraseAlternative(label, parse_criterion(a, ALTERNATIVE_KEYS)))
    unique(t.where, "alternative labels", (a.label for a in alternatives))
    labels = [a.label for a in alternatives]
    default = t.text("default", labels[0])
    if default not in labels:
        raise ConfigurationError(f"{t.where} default: {default!r} is not one of {labels}")
    return (), tuple(alternatives), labels.index(default)
