"""``fundamentals@v3``: shares outstanding, the count a year earlier and the market-cap status.

Inputs: ``instruments/shares`` (SEC company facts; every fact FILED on or before the session,
point in time by filing date), the session's ``price_stats@v2`` close, and ``events/split``
by event date. One row per instrument with a close or a share count on the session.

Which count (per instrument, among facts filed on or before the session):

- ``dei`` (cover-page ``EntityCommonStockSharesOutstanding``): the latest filed (then the
  latest period end), used while the company still tags it, i.e. its latest ``dei`` fact was
  filed no earlier than its latest weighted fact;
- else ``weighted_basic`` (``WeightedAverageNumberOfSharesOutstandingBasic`` of the latest
  filing's current period): the fallback for filers that stopped tagging the cover page
  (most multi-class issuers).

Counts are company totals: every class of a CIK (GOOGL and GOOG) gets the same count, so
``market_cap`` is the total times this class's close, which misstates issuers whose classes
trade at very different prices (BRK.A / BRK.B; Berkshire's facts are also years stale).

Splits after the count are applied (``shares x ratio``): after ``period_end`` for a cover
count (the count is as of that date); after ``filed`` for a weighted average (filers restate
it for splits before they file).

    shares_outstanding  the count, split-adjusted to the session
    shares_outstanding_year_ago
                        the count of the same kind a year earlier, split-adjusted likewise
    shares_as_of        its period end (the cover date, or the end of the averaged period)
    shares_filed        the filing date that made it public
    shares_source       dei / weighted_basic
    market_cap_status   OK / NO_SHARES (no fact: ETFs, funds, no CIK) / STALE (period end more
                        than ``stale_days`` before the session) / NO_PRICE (no close)

``shares_outstanding_year_ago`` is the count of the same concept as the chosen one (a cover
count against a cover count, a weighted average against a weighted average: the two differ by
definition) among the facts filed on or before the session, whose period ended 9 to 15 months
before ``shares_as_of``, the one closest to a year before it (a later filing of the same period,
an amendment, wins a tie); null when there is none. It is split-adjusted by the same rule as
the current count, to the session's share terms, so a split in between does not read as
dilution. The expression ``shares_change_yoy`` is the ratio minus one.

v2 (ADR 0023 step 3) stores ``shares_outstanding`` as a 32-bit float and drops
``market_cap``: it is the expression feature ``market_cap`` (``shares_outstanding x close``
when the status is OK; ``config/site/features/fundamentals.toml``), computed on read. The
status stays here: it needs the count's period end against the session date.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "fundamentals"
VERSION = 3
SHARES = "instruments/shares"
PRICE_STATS = "rollups/instrument/price_stats@v2"
SPLITS = "events/split"
DEI, WEIGHTED = "dei", "weighted_basic"
YEAR = 365  # days before shares_as_of the year-ago count's period ideally ended
YEAR_AGO = (274, 456)  # days before shares_as_of that period may end: 9 to 15 months

_NO_SHARES = "no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES"
_FACTS = (f"{SHARES}.shares", f"{SHARES}.concept", f"{SHARES}.filed", f"{SHARES}.period_end")

FEATURES = (
    Feature(
        "shares_outstanding", "float32", "shares",
        "Shares outstanding (company total of every class), split-adjusted to the session: "
        "the latest cover-page count (dei) while the company tags it, else the latest "
        "weighted average basic",
        _NO_SHARES, valid_range=(0, None), inputs=(*_FACTS, f"{SPLITS}.ratio"),
    ),
    Feature(
        "shares_outstanding_year_ago", "float32", "shares",
        "Shares outstanding a year earlier: the count of the same kind (cover or weighted "
        "average) whose period ended 9 to 15 months before shares_as_of, the one closest to a "
        "year, split-adjusted to the session: the base of shares_change_yoy",
        _NO_SHARES + "; or no count of that kind with a period ending 9 to 15 months before "
        "shares_as_of is filed by the session (a newer filer, or a company that began tagging "
        "the cover page less than a year ago)",
        valid_range=(0, None), inputs=(*_FACTS, f"{SPLITS}.ratio"),
    ),
    Feature(
        "shares_as_of", "date", "date",
        "The count's period end (the cover date, or the end of the averaged period)",
        _NO_SHARES, inputs=(f"{SHARES}.period_end",),
    ),
    Feature(
        "shares_filed", "date", "date", "The filing date that made the count public",
        _NO_SHARES, inputs=(f"{SHARES}.filed",),
    ),
    Feature(
        "shares_source", "str", "category",
        "Which count: dei (cover page) or weighted_basic (weighted average basic)",
        _NO_SHARES, "label", categories=(DEI, WEIGHTED), inputs=(f"{SHARES}.concept",),
    ),
    Feature(
        "market_cap_status", "str", "category",
        "OK; NO_SHARES (no count); STALE (period end more than stale_days, 400, before the "
        "session; the count is still shown); NO_PRICE (no close)",
        "never", "label", categories=("OK", "NO_SHARES", "STALE", "NO_PRICE"),
        inputs=("fundamentals.shares_outstanding@v3", "price_stats.close@v2"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


@dataclass(frozen=True)
class FundamentalsParams:
    stale_days: int = 400  # a count whose period ended longer ago is STALE (no market cap)

    def __post_init__(self) -> None:
        if self.stale_days < 1:
            raise ValueError(f"stale_days must be >= 1, got {self.stale_days}")


def split_lookback(p: FundamentalsParams) -> int:
    """Sessions of splits loaded: more than ``stale_days`` plus the year-ago window (the
    oldest count ``year_ago`` reads) in calendar days."""
    return int((p.stale_days + YEAR_AGO[1]) * 252 / 365) + 10


def _latest(facts: pd.DataFrame, concept: str) -> pd.DataFrame:
    rows = facts[facts["concept"] == concept]
    order = ["instrument_id", "filed", "period_end"]
    return rows.sort_values(order, kind="stable").drop_duplicates("instrument_id", keep="last")


def choose(facts: pd.DataFrame | None) -> pd.DataFrame:
    """Per instrument: the count to use (``instrument_id``, ``shares``, ``period_end``,
    ``filed``, ``concept``) among ``facts`` (already filed on or before the session)."""
    columns = ["instrument_id", "shares", "period_end", "filed", "concept"]
    if facts is None or facts.empty:
        return pd.DataFrame(columns=columns)
    dei = _latest(facts, DEI).set_index("instrument_id")
    weighted = _latest(facts, WEIGHTED).set_index("instrument_id")
    later = weighted["filed"].reindex(dei.index)
    keep = later.isna() | (dei["filed"] >= later.fillna(dei["filed"]))
    dei = dei[keep.to_numpy()]
    chosen = pd.concat([dei, weighted[~weighted.index.isin(dei.index)]])
    return chosen.reset_index()[columns].sort_values("instrument_id").reset_index(drop=True)


def year_ago(facts: pd.DataFrame | None, chosen: pd.DataFrame) -> pd.DataFrame:
    """Per chosen count: the count of the same concept a year earlier among ``facts`` (already
    filed on or before the session): the fact whose period ended ``YEAR_AGO`` days before the
    chosen count's, the one closest to ``YEAR``, the latest filed on a tie. Columns as
    ``choose``; instruments with no such count are absent."""
    columns = ["instrument_id", "shares", "period_end", "filed", "concept"]
    if facts is None or facts.empty or chosen.empty:
        return pd.DataFrame(columns=columns)
    now = chosen[["instrument_id", "concept", "period_end"]].rename(columns={"period_end": "now"})
    now = now.assign(now=pd.to_datetime(now["now"]))
    past = facts[facts["concept"].isin([DEI, WEIGHTED])]
    past = past[past["shares"].notna() & past["period_end"].notna()][columns]
    both = now.merge(past, on=["instrument_id", "concept"])
    age = (both["now"] - pd.to_datetime(both["period_end"])).dt.days
    both = both.assign(miss=(age - YEAR).abs())[age.between(*YEAR_AGO)]
    both = both.sort_values(
        ["instrument_id", "miss", "filed"], ascending=[True, True, False], kind="stable"
    )
    best = both.drop_duplicates("instrument_id", keep="first")
    return best[columns].sort_values("instrument_id").reset_index(drop=True)


def split_factor(chosen: pd.DataFrame, splits: pd.DataFrame | None, session: date) -> np.ndarray:
    """Per chosen count: the product of split ratios after its count date, up to the session."""
    factor = np.ones(len(chosen))
    if splits is None or splits.empty or chosen.empty:
        return factor
    after = np.where(chosen["concept"] == DEI, chosen["period_end"], chosen["filed"])
    ids = chosen["instrument_id"].astype(str).to_numpy()
    for iid, when, ratio in zip(
        splits["instrument_id"].astype(str), splits["event_date"], splits["ratio"].astype(float),
        strict=True,
    ):  # fmt: skip
        if when <= session:
            factor[(ids == iid) & np.array([d < when for d in after])] *= ratio
    return factor


def compute(inputs: Inputs, session: date, p: FundamentalsParams) -> pd.DataFrame:
    stats = inputs[PRICE_STATS]
    assert stats is not None  # required input
    today = stats[stats["session_date"] == session][["instrument_id", "close"]]
    splits = inputs.get(SPLITS)
    chosen = choose(inputs.get(SHARES))
    before = year_ago(inputs.get(SHARES), chosen)
    chosen["shares"] = chosen["shares"].astype(float) * split_factor(chosen, splits, session)
    before["shares"] = before["shares"].astype(float) * split_factor(before, splits, session)
    before = before[["instrument_id", "shares"]].rename(columns={"shares": "ago"})
    out = today.merge(chosen, on="instrument_id", how="outer").sort_values("instrument_id")
    out = out.merge(before, on="instrument_id", how="left")
    close = pd.to_numeric(out["close"], errors="coerce").to_numpy(dtype=float)
    shares = pd.to_numeric(out["shares"], errors="coerce").to_numpy(dtype=float)
    ago = pd.to_numeric(out["ago"], errors="coerce").to_numpy(dtype=float)
    oldest = session - timedelta(days=p.stale_days)
    stale = np.array([d is not None and not pd.isna(d) and d < oldest for d in out["period_end"]])
    status = np.select(
        [np.isnan(shares), stale, ~(close > 0)], ["NO_SHARES", "STALE", "NO_PRICE"], "OK"
    )
    return pd.DataFrame(
        {
            "instrument_id": out["instrument_id"].astype(str).to_numpy(),
            "shares_outstanding": shares,
            "shares_outstanding_year_ago": ago,
            "shares_as_of": out["period_end"].to_numpy(),
            "shares_filed": out["filed"].to_numpy(),
            "shares_source": out["concept"].to_numpy(),
            "market_cap_status": status,
        }
    )


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Shares outstanding and the count a year earlier (SEC company facts, point in time by "
    "filing date) and its status",
    (
        Input(PRICE_STATS),
        Input(SHARES, required=False),
        Input(SPLITS, lookback=split_lookback, required=False),
    ),
    FEATURES,
    compute,
    FundamentalsParams(),
)
