"""Where a regime card's value comes from, derived from the feature catalogue, never typed by
hand: the card's value and verdict features -> their ``inputs``, followed through every feature
they name -> the leaves, each a macro series (``series:<KEY>``, described by
``config/site/macro.toml``: code, cadence, release lag, licence, terms) or a stored table
(``bars/1d.close`` -> ``bars/1d``, described by a ``[[source]]`` of
``config/site/regime/cards.toml``). A leaf neither describes has no source (a fitness test
keeps every shipped card's leaves resolved); a card whose feature is not in the catalogue yet
has none. A card whose source is chosen per session (``source_by``: the S&P 500 trend from
SPY's bars or the SPX level) lists both; ``activate`` marks the one the session's value names.

Provenance per series, for ``ctx.session``: its latest observation the session knew, with that
value's vintage date and kind (``series_as_of`` with ``lookback=0``: ``known_window`` over the
series' stored vintages), and ``first_vintage``, the series' earliest ALFRED vintage the
session knew: before it the stored history is the figures as first vintaged, not as they were
known then ("before <date> these are today's revised figures"). ``None`` for a lagged
(unrevised) series. One read of the vintages per publish (``visible_seq``) and session."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date

import pandas as pd

from algotrade.config.site.macro import MacroSeries, MacroSettings
from algotrade.config.site.regime.cards import InputSource, SourceSwitch
from algotrade.data.macro.series import known_window, stored_vintages
from algotrade.features.expressions.feature_set import FeatureSet
from algotrade.features.framework.feature import SERIES_REF, is_feature_ref, is_series_ref
from algotrade.services.read.context import ReadContext

FRED_URL = "https://fred.stlouisfed.org/series/"
ALFRED = "alfred"  # macro/series vintage_kind of an ALFRED vintage
SOURCE_NAMES = {"fred": "FRED", "published": "Published file"}


@dataclass(frozen=True)
class IndicatorSource:
    """One source of a card's value. ``series``: the ``macro.toml`` key (``None`` for a stored
    table); ``release_lag_days``, ``terms`` and the provenance only for a series;
    ``last_observation`` / ``vintage_date`` / ``vintage_kind``: its latest observation the
    session knew and when that value became public (``alfred`` or ``lagged``);
    ``first_vintage``: its earliest ALFRED vintage the session knew (``None``: lagged, or
    nothing stored). ``input``: the lineage leaf it describes (``series:SPX``, ``bars/1d``);
    ``active``: it fed the value for the session (``activate``: false for the source a
    per-session switch did not choose)."""

    input: str
    label: str
    series: str | None
    cadence: str
    release_lag_days: int | None
    url: str | None
    licence: str
    terms: str | None
    last_observation: date | None = None
    vintage_date: date | None = None
    vintage_kind: str | None = None
    first_vintage: date | None = None
    active: bool = True


def leaves(features: FeatureSet, names: Sequence[str]) -> tuple[str, ...]:
    """The lineage leaves of ``names`` in first-seen order: ``series:<KEY>`` refs, stored tables
    (a raw ``<table>.<column>`` input's table) and feature refs the catalogue does not have."""
    out: dict[str, None] = {}
    seen: set[str] = set()

    def visit(ref: str) -> None:
        if ref in seen:
            return
        seen.add(ref)
        if is_series_ref(ref):
            out[ref] = None
            return
        feature = features.feature(ref)
        if feature is None:
            out[ref] = None  # a feature the catalogue does not have: resolves to no source
            return
        for child in feature.inputs:
            if is_series_ref(child) or is_feature_ref(child):
                visit(child)
            else:
                out[child.rsplit(".", 1)[0]] = None

    for name in names:
        if features.feature(name) is not None:
            visit(name)
    return tuple(out)


def series_of(leaf: str, macro: MacroSettings) -> MacroSeries | None:
    """The registry series a ``series:<KEY>`` leaf names (``None``: not a series, or unknown)."""
    key = leaf.removeprefix(SERIES_REF) if is_series_ref(leaf) else None
    return macro.by_key(key) if key is not None and key in macro.keys else None


def table_source(leaf: str, sources: Iterable[InputSource]) -> InputSource | None:
    return next((s for s in sources if s.input == leaf), None)


def _described(leaf: str, s: MacroSeries) -> IndicatorSource:
    url = FRED_URL + s.vendor_code if s.source == "fred" else s.url
    label = f"{SOURCE_NAMES.get(s.source, s.source)} {s.vendor_code}"
    return IndicatorSource(
        leaf, label, s.key, s.cadence, s.release_lag_days, url or None, s.licence, s.terms
    )


def _table(s: InputSource) -> IndicatorSource:
    return IndicatorSource(s.input, s.label, None, s.cadence, None, s.url, "open", None)


@dataclass(frozen=True)
class Provenance:
    last_observation: date
    vintage_date: date
    vintage_kind: str


def _first_vintages(frame: pd.DataFrame) -> dict[str, date]:
    alfred = frame[frame["vintage_kind"] == ALFRED]
    return {str(k): v for k, v in alfred.groupby("instrument_id")["vintage_date"].min().items()}


def _provenance(
    ctx: ReadContext, ids: tuple[str, ...]
) -> tuple[Mapping[str, Provenance], Mapping[str, date]]:
    """Per instrument id: the latest observation ``ctx.session`` knew, and the earliest ALFRED
    vintage stored (cached per publish; the caller drops one later than the session)."""
    seq, day = ctx.reader.visible_seq(), ctx.session.date
    latest_key = ("regime-source-latest", ids, day, seq)  # ADR 0022
    first_key = ("regime-source-first-vintage", ids, seq)
    latest, first = ctx.cache.get(latest_key), ctx.cache.get(first_key)
    if latest is None or first is None:
        frame = stored_vintages(ctx.reader, ids)
        known = known_window(frame, day, 0)  # series_as_of(lookback=0) over this one read
        newest = known.sort_values("obs_date", kind="stable").drop_duplicates(
            "instrument_id", keep="last"
        )
        columns = ("instrument_id", "obs_date", "vintage_date", "vintage_kind")
        latest = {
            str(iid): Provenance(obs, vintage, str(kind))
            for iid, obs, vintage, kind in zip(*(newest[c] for c in columns), strict=True)
        }
        first = _first_vintages(frame)
        ctx.cache.put(latest_key, latest)
        ctx.cache.put(first_key, first)
    return latest, first


def load_sources(
    ctx: ReadContext,
    names: Mapping[str, Sequence[str]],
    macro: MacroSettings,
    tables: Sequence[InputSource],
) -> dict[str, tuple[IndicatorSource, ...]]:
    """Per card key, the sources its features (``names``: card key -> its value and verdict
    features) reach, in lineage order, with each series' provenance for ``ctx.session``."""
    by_card: dict[str, list[IndicatorSource | tuple[str, MacroSeries]]] = {}
    for key, features in names.items():
        found: list[IndicatorSource | tuple[str, MacroSeries]] = []
        for leaf in leaves(ctx.features, features):
            series, table = series_of(leaf, macro), table_source(leaf, tables)
            if series is not None:
                found.append((leaf, series))
            elif table is not None:
                found.append(_table(table))
        by_card[key] = found
    ids = tuple(sorted({s[1].instrument_id for f in by_card.values() for s in f
                        if isinstance(s, tuple)}))  # fmt: skip
    latest, first = _provenance(ctx, ids) if ids else ({}, {})
    day = ctx.session.date

    def described(found: IndicatorSource | tuple[str, MacroSeries]) -> IndicatorSource:
        if isinstance(found, IndicatorSource):
            return found
        leaf, s = found
        p, earliest = latest.get(s.instrument_id), first.get(s.instrument_id)
        return replace(
            _described(leaf, s),
            last_observation=p.last_observation if p else None,
            vintage_date=p.vintage_date if p else None,
            vintage_kind=p.vintage_kind if p else None,
            first_vintage=earliest if earliest is not None and earliest <= day else None,
        )

    return {key: tuple(described(s) for s in found) for key, found in by_card.items()}


def activate(
    found: tuple[IndicatorSource, ...], switch: SourceSwitch | None, chosen: object
) -> tuple[IndicatorSource, ...]:
    """``found`` with the sources ``switch`` governs active only when ``chosen`` (the
    session's value of ``switch.feature``; ``None``: not stored) names them; the others stay
    active. A value the switch does not list activates none of its sources."""
    if switch is None:
        return found
    governed = {i for inputs in switch.inputs.values() for i in inputs}
    picked = set(switch.inputs.get(str(chosen), ())) if chosen is not None else set()
    return tuple(replace(s, active=s.input not in governed or s.input in picked) for s in found)
