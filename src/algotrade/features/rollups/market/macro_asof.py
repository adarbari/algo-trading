"""``market_macro_asof@v1``: when each macro series the regime cards rest on became known, one
``MKT:US`` row per session (ADR 0047, ADR 0048, ADR 0007; the provenance panel of ``/regime``).

Per series key ``<k>`` (``SERIES``: the series the shipped regime cards reach, checked against
the cards by a test), four columns, point in time by vintage exactly as ``macro/series`` is read
(``data.macro.series``: ``vintage_date <= session``, never a later revision):

    <k>_last_obs_date   the latest observation the session knew
    <k>_vintage_date    the date that observation's value became public (the vintage it knew)
    <k>_vintage_kind    ``alfred`` (a real vintage) or ``lagged`` (observation date + the
                        release lag, an unrevised series)
    <k>_first_vintage   the series' earliest ALFRED vintage on or before the session: before it
                        the stored history is the figures as first vintaged, not as they were
                        known then (null: a lagged series, or none known yet)

They are what ``services.read.regime.sources`` reads instead of the 2.9 million stored vintages
(it recomputes from those for a session with no row, a series without columns here, or a
series with no observation). Every column is null (UNKNOWN, never zero) when the series has no
observation known by the session. The columns hold dates, not values: a series under the
personal licence (ADR 0028, ADR 0069) keeps the licence on each of its columns, as the
expression features over it inherit it.
"""

from dataclasses import dataclass
from datetime import date

import pandas as pd

from algotrade.core.model.instruments import index_id, macro_id, market_id
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs
from algotrade.features.framework.feature import Feature, Kind, Licence

NAME = "macro_asof"
VERSION = 1
MACRO = "macro/series"
FIRST = "macro/first_vintages"
KINDS = ("alfred", "lagged")


@dataclass(frozen=True)
class Use:
    """One series: whether it is an index level (``IDX:``) and under the personal licence (the
    registry's, ``config/site/macro.toml``: a test checks both)."""

    index: bool = False
    personal: bool = False

    def id(self, key: str) -> str:
        return index_id(key) if self.index else macro_id(key)


SERIES: dict[str, Use] = {
    "T10Y3M": Use(),
    "BAMLH0A0HYM2": Use(personal=True),
    "UNRATE": Use(),
    "NFCI": Use(),
    "SPX": Use(index=True, personal=True),
    "VIX": Use(index=True, personal=True),
    "VIX3M": Use(index=True, personal=True),
}
ID = {key: use.id(key) for key, use in SERIES.items()}
_NONE = "the series has no observation known by the session (no FRED key, or before it starts)"


def column(key: str, field: str) -> str:
    """The stored column of ``field`` (``last_obs_date`` ...) of series ``key``."""
    return f"{key.lower()}_{field}"


def _features(key: str, use: Use) -> tuple[Feature, ...]:
    licence: Licence = "personal" if use.personal else "open"
    inputs = (f"series:{key}",)

    def one(
        field: str,
        dtype: str,
        description: str,
        null: str = _NONE,
        kind: Kind = "window",
        categories: tuple[str, ...] = (),
    ) -> Feature:
        return Feature(
            column(key, field), dtype, "date" if dtype == "date" else "category",
            f"{key}: {description}", null, kind=kind, categories=categories,
            inputs=inputs, licence=licence,
        )  # fmt: skip

    return (
        one("last_obs_date", "date", "the latest observation known by the session"),
        one("vintage_date", "date", "the date that observation's value became public"),
        one("vintage_kind", "str", "alfred (a real vintage) or lagged (observation date plus "
            "the release lag)", kind="label", categories=KINDS),
        one("first_vintage", "date", "the earliest ALFRED vintage known by the session: before "
            "it the stored history is the figures as first vintaged, not as known then",
            "the series is unrevised (lagged), or its first ALFRED vintage is after the session"),
    )  # fmt: skip


FEATURES = tuple(f for key, use in SERIES.items() for f in _features(key, use))
COLUMNS = [f.name for f in FEATURES]


def _day(value: object) -> date | None:
    return None if value is None else pd.Timestamp(str(value)).date()


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    known, firsts = inputs[MACRO], inputs[FIRST]
    row: dict[str, object] = {"instrument_id": market_id("US")}
    if known is not None and not known.empty:
        # ``data.macro.series.latest_known``'s rule over the input's rows: the newest observation
        newest = known.sort_values("obs_date", kind="stable").drop_duplicates(
            "instrument_id", keep="last"
        )
        by_id = newest.set_index("instrument_id")
    else:
        by_id = pd.DataFrame(columns=["obs_date", "vintage_date", "vintage_kind"])
    first = (
        {}
        if firsts is None
        else dict(zip(firsts["instrument_id"], firsts["first_vintage"], strict=True))
    )
    for key, iid in ID.items():
        found = by_id.loc[iid] if iid in by_id.index else None
        row[column(key, "last_obs_date")] = None if found is None else found["obs_date"]
        row[column(key, "vintage_date")] = None if found is None else found["vintage_date"]
        row[column(key, "vintage_kind")] = None if found is None else found["vintage_kind"]
        row[column(key, "first_vintage")] = _day(first.get(iid))
    return pd.DataFrame([row], columns=["instrument_id", *COLUMNS])


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "When each macro series the regime cards rest on became known: its latest observation "
    "known by the session, the date and kind of that vintage and the series' first ALFRED "
    "vintage (provenance, point in time by vintage)",
    (
        Input(MACRO, lookback=0, required=False, ids=tuple(ID.values())),
        Input(FIRST, required=False, ids=tuple(ID.values())),
    ),
    FEATURES,
    compute,
    entity="market",
)
