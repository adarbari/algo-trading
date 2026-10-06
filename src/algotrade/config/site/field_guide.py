"""Site field guide (ADR 0041, amended 2026-10-06): ``config/site/field_guide/*.toml`` (one file
per theme, plus the situations) typed into frozen dataclasses. Per catalogue field: how to read
it (``reads``), the usual criterion for each intent a trader has (``uses``: op, value, mode,
tolerance, as the rule grammar takes them), the caveats (when the reading lies, each naming what
to check) and the sources; plus the ``situations`` that fool several thresholds at once (a
pending takeover, an earnings gap in the window). One source for the Builder's field help, the
generated page ``docs/data/field-guide.md`` and the drafting prompt. The loader checks shape and
vocabulary only; that every name is a catalogue field and every value fits its type and range is
``tests/architecture/test_features.py``."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from algotrade.config.site.fields import Table, reject_secrets
from algotrade.core.model.errors import ConfigurationError

FIELD_KEYS = ("name", "theme", "reads", "caveats", "sources", "use")
USE_KEYS = ("for", "op", "value", "mode", "tolerance", "on_miss", "note")
SITUATION_KEYS = ("name", "signs", "affects", "do")
OPS = ("eq", "ne", "in", "not_in", "gt", "gte", "lt", "lte", "between", "is_null", "not_null")
VALUELESS_OPS = ("is_null", "not_null")
MODES = ("hard", "soft", "score")
ON_MISS = ("WATCH", "LIQUIDITY_RISK", "EVENT_RISK")

Tolerance = float | Mapping[str, float] | None


@dataclass(frozen=True)
class GuideUse:
    """One intent and its criterion: ``intent`` ("oversold bounce"), ``op`` / ``value`` /
    ``mode`` / ``tolerance`` / ``on_miss`` as a rule screen's criterion takes them
    (``docs/screeners/rules.md``), ``note`` on how to combine it."""

    intent: str
    op: str
    value: Any = None
    mode: str = "hard"
    tolerance: Tolerance = None
    on_miss: str = ""
    note: str = ""


@dataclass(frozen=True)
class FieldGuideEntry:
    """One catalogue field: ``theme`` (the page groups by it), ``reads`` (what the number
    means, low to high), ``uses`` (file order), ``caveats`` (when the reading lies, each
    ending with what to check), ``sources``."""

    name: str
    theme: str
    reads: str
    uses: tuple[GuideUse, ...] = ()
    caveats: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class Situation:
    """One state of the world that fools several thresholds: ``signs`` (how it shows in the
    catalogue), ``affects`` (the fields it distorts), ``do`` (what a screen does about it)."""

    name: str
    signs: str
    affects: tuple[str, ...]
    do: str


@dataclass(frozen=True)
class FieldGuideSettings:
    """``config/site/field_guide/*.toml``: the entries and situations in file order (none
    without files)."""

    fields: tuple[FieldGuideEntry, ...] = ()
    situations: tuple[Situation, ...] = ()

    @classmethod
    def from_documents(cls, docs: Mapping[str, Mapping[str, Any] | None]) -> "FieldGuideSettings":
        """The files of ``config/site/field_guide/`` by name, in the order given (the loader
        gives file-name order); a field guided in two files is an error."""
        fields: list[FieldGuideEntry] = []
        situations: list[Situation] = []
        for name, doc in docs.items():
            where = f"field_guide/{name}.toml"
            reject_secrets(doc or {}, where)
            root = Table(doc, where)
            root.only(("field", "situation"))
            fields += [
                _entry(Table(e, f"{where} [[field]][{i}]"))
                for i, e in enumerate(_tables(root, "field"))
            ]
            situations += [
                _situation(Table(e, f"{where} [[situation]][{i}]"))
                for i, e in enumerate(_tables(root, "situation"))
            ]
        names = [f.name for f in fields]
        if len(set(names)) != len(names):
            dupes = sorted({n for n in names if names.count(n) > 1})
            raise ConfigurationError(f"field_guide: a field is guided twice: {dupes}")
        return cls(tuple(fields), tuple(situations))

    @classmethod
    def from_document(cls, doc: Mapping[str, Any] | None) -> "FieldGuideSettings":
        """One file's worth (tests, and a guide kept in one file)."""
        return cls.from_documents({"field_guide": doc})

    def entry(self, name: str) -> FieldGuideEntry | None:
        """The entry for a catalogue field (``None``: not guided)."""
        return next((f for f in self.fields if f.name == name), None)


def _tables(t: Table, key: str) -> list[Mapping[str, Any]]:
    raw = t.raw(key) or []
    if not isinstance(raw, list) or not all(isinstance(e, Mapping) for e in raw):
        raise ConfigurationError(f"{t.where} {key}: expected a list of tables ([[{key}]])")
    return raw


def _required(t: Table, key: str) -> str:
    value = t.text(key, "").strip()
    if not value:
        raise ConfigurationError(f"{t.where} {key}: expected a non-empty string")
    return value


def _lines(t: Table, key: str) -> tuple[str, ...]:
    values = tuple(" ".join(s.split()) for s in t.strings(key, ()))
    if not all(values):
        raise ConfigurationError(f"{t.where} {key}: expected non-empty strings")
    return values


def _entry(t: Table) -> FieldGuideEntry:
    t.only(FIELD_KEYS)
    name = _required(t, "name")
    uses = tuple(_use(Table(u, f"{t.where} [[use]][{i}]")) for i, u in enumerate(_tables(t, "use")))
    return FieldGuideEntry(
        name=name,
        theme=_required(t, "theme"),
        reads=" ".join(_required(t, "reads").split()),
        uses=uses,
        caveats=_lines(t, "caveats"),
        sources=_lines(t, "sources"),
    )


def _use(t: Table) -> GuideUse:
    t.only(USE_KEYS)
    op = t.choice("op", "", OPS) if t.raw("op") is not None else ""
    if not op:
        raise ConfigurationError(f"{t.where} op: expected one of {', '.join(OPS)}")
    value = t.raw("value")
    if op in VALUELESS_OPS:
        if value is not None:
            raise ConfigurationError(f"{t.where} value: {op} takes none")
    elif value is None:
        raise ConfigurationError(f"{t.where} value: expected a value for {op}")
    mode = t.choice("mode", "hard", MODES)
    tolerance = _tolerance(t)
    if mode == "soft" and tolerance is None:
        raise ConfigurationError(f"{t.where} tolerance: a soft criterion needs one")
    if mode == "hard" and tolerance is not None:
        raise ConfigurationError(f"{t.where} tolerance: a hard criterion takes none")
    on_miss = t.choice("on_miss", "", ON_MISS) if t.raw("on_miss") is not None else ""
    if on_miss and mode != "soft":
        raise ConfigurationError(f"{t.where} on_miss: soft criteria only")
    return GuideUse(
        intent=_required(t, "for"),
        op=op,
        value=value,
        mode=mode,
        tolerance=tolerance,
        on_miss=on_miss,
        note=" ".join(t.text("note", "").split()),
    )


def _tolerance(t: Table) -> Tolerance:
    raw = t.raw("tolerance")
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, int | float | Mapping):
        raise ConfigurationError(f"{t.where} tolerance: expected a number or {{ relative = r }}")
    if isinstance(raw, Mapping):
        relative = Table(raw, f"{t.where} tolerance")
        relative.only(("relative",))
        return {"relative": relative.fraction("relative", 0.0)}
    if raw < 0:
        raise ConfigurationError(f"{t.where} tolerance: expected a number >= 0")
    return raw


def _situation(t: Table) -> Situation:
    t.only(SITUATION_KEYS)
    affects = _lines(t, "affects")
    if not affects:
        raise ConfigurationError(f"{t.where} affects: expected one or more catalogue field names")
    return Situation(
        name=_required(t, "name"),
        signs=" ".join(_required(t, "signs").split()),
        affects=affects,
        do=" ".join(_required(t, "do").split()),
    )
