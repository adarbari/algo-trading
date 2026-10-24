"""``fundamentals@v5``: shares outstanding, the count a year earlier and the market-cap status.

Inputs: ``instruments/shares`` (SEC company facts) read as ``instruments/shares_accepted``: every
fact public at the session's CLOSE, point in time by the instant SEC ACCEPTED the filing
(16:00 New York time, 13:00 on an early close; a fact without an acceptance time counts from
the session after its filing date), the session's ``price_stats@v2`` close, and ``events/split``
by event date. v3 counted every fact ``filed <= session``, a date: a filing accepted after
the close counted at that close, a one-session lookahead (ADR 0067 amendment; ``financials@v3``
has the same fix); no column changed. One row per instrument with a close or a share count on
the session.

Which count (per instrument, among facts public by the session's close):

- ``dei`` (cover-page ``EntityCommonStockSharesOutstanding``): the latest filed (then the
  latest period end), used while the company still tags it, i.e. its latest ``dei`` fact was
  filed no earlier than its latest weighted fact;
- else ``weighted_basic`` (``WeightedAverageNumberOfSharesOutstandingBasic`` of the latest
  filing's current period): the fallback for filers that stopped tagging the cover page
  (most multi-class issuers);
- else ``ifrs_weighted`` (``ifrs-full:WeightedAverageShares``, the same weighted average of the
  latest filing's current period): foreign filers with IFRS facts only (AZN, BP, TECK, MFC,
  RCI). Only for an instrument whose ``security_type`` is known and is not ``ADR``: the fact
  counts ordinary shares, and an ADR's ratio of shares per ADS is not stored, so the count
  times the ADR's close would misstate the market cap. A foreign ordinary listing (COMMON_STOCK)
  needs no ratio. An ADR's own ``dei`` / ``weighted_basic`` counts are kept as before.

v5 adds ``ifrs_weighted`` to ``shares_source`` and reads ``instruments/reference`` for the
security type; every v4 column is unchanged, and a v4 value is the same in v5 (only
instruments that had NO_SHARES can gain a count).

Counts are company totals: every class of a CIK (GOOGL and GOOG) gets the same count, so
``market_cap`` is the total times this class's close, which misstates issuers whose classes
trade at very different prices (BRK.A / BRK.B; Berkshire's facts are also years stale).

Splits after the count are applied (``shares x ratio``): after ``period_end`` for a cover
count (the count is as of that date); after ``filed`` for a weighted average, IFRS included
(filers restate it for splits before they file).

    shares_outstanding  the count, split-adjusted to the session
    shares_outstanding_year_ago
                        the count of the same kind a year earlier, split-adjusted likewise
    shares_as_of        its period end (the cover date, or the end of the averaged period)
    shares_filed        the filing date that made it public
    shares_source       dei / weighted_basic / ifrs_weighted
    market_cap_status   OK / NO_SHARES (no fact: ETFs, funds, no CIK) / STALE (period end more
                        than ``stale_days`` before the session) / NO_PRICE (no close)

``shares_outstanding_year_ago`` is the count of the same concept as the chosen one (a cover
count against a cover count, a weighted average against a weighted average: the two differ by
definition) among the facts public by the session's close, whose period ended 9 to 15 months
before ``shares_as_of``, the one closest to a year before it (a later filing of the same period,
an amendment, wins a tie); null when there is none. It is split-adjusted by the same rule as
the current count, to the session's share terms, so a split in between does not read as
dilution. The expression ``shares_change_yoy`` is the ratio minus one.

v2 (ADR 0023 step 3) stores ``shares_outstanding`` as a 32-bit float and drops
``market_cap``: it is the expression feature ``market_cap`` (``shares_outstanding x close``
when the status is OK; ``config/site/features/company/fundamentals.toml``), computed on read. The
status stays here: it needs the count's period end against the session date.
"""

from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "fundamentals"
VERSION = 5
SHARES = "instruments/shares_accepted"  # by acceptance session, not by filing date
PRICE_STATS = "rollups/instrument/price_stats@v2"
SPLITS = "events/split"
DEI, WEIGHTED, IFRS = "dei", "weighted_basic", "ifrs_weighted"
REFERENCE = "instruments/reference"
ADR = "ADR"  # an ADS count is not the ordinary-share count the IFRS fact reports
YEAR = 365  # days before shares_as_of the year-ago count's period ideally ended
YEAR_AGO = (274, 456)  # days before shares_as_of that period may end: 9 to 15 months

_NO_SHARES = "no share-count fact public by the session's close (ETFs, funds, no CIK): NO_SHARES"
_FACTS = (
    f"{SHARES}.shares", f"{SHARES}.concept", f"{SHARES}.filed", f"{SHARES}.period_end",
    f"{REFERENCE}.security_type",
)  # fmt: skip

FEATURES = (
    Feature(
        "shares_outstanding", "float32", "shares",
        "Shares outstanding (company total of every class), split-adjusted to the session: "
        "the latest cover-page count (dei) while the company tags it, else the latest "
        "weighted average basic (us-gaap), else the latest IFRS weighted average (ordinary "
        "listings of foreign filers, never an ADR)",
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
        "shares_filed", "date", "date",
        "The filing date of the filing that made the count public (it counts from the session "
        "whose close is after SEC's acceptance of it)",
        _NO_SHARES, inputs=(f"{SHARES}.filed",),
    ),
    Feature(
        "shares_source", "str", "category",
        "Which count: dei (cover page), weighted_basic (weighted average basic, us-gaap) or "
        "ifrs_weighted (IFRS weighted average, foreign ordinary listings only)",
        _NO_SHARES, "label", categories=(DEI, WEIGHTED, IFRS),
        inputs=(f"{SHARES}.concept", f"{REFERENCE}.security_type"),
    ),
    Feature(
        "market_cap_status", "str", "category",
        "OK; NO_SHARES (no count); STALE (period end more than stale_days, 400, before the "
        "session; the count is still shown); NO_PRICE (no close)",
        "never", "label", categories=("OK", "NO_SHARES", "STALE", "NO_PRICE"),
        inputs=("fundamentals.shares_outstanding@v5", "price_stats.close@v2"),
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


def ifrs_allowed(reference: pd.DataFrame | None) -> set[str]:
    """Instruments the IFRS weighted average may count for: a known security type that is not
    an ADR (no reference snapshot: none, an unknown type is not assumed ordinary)."""
    if reference is None or "security_type" not in reference.columns:
        return set()
    kind = reference["security_type"]
    return set(reference.loc[kind.notna() & (kind != ADR), "instrument_id"].astype(str))


def choose(facts: pd.DataFrame | None, ifrs_ids: set[str] | None = None) -> pd.DataFrame:
    """Per instrument: the count to use (``instrument_id``, ``shares``, ``period_end``,
    ``filed``, ``concept``) among ``facts`` (already public by the session's close);
    ``ifrs_weighted`` facts count only for ``ifrs_ids``, the last choice."""
    columns = ["instrument_id", "shares", "period_end", "filed", "concept"]
    if facts is None or facts.empty:
        return pd.DataFrame(columns=columns)
    dei = _latest(facts, DEI).set_index("instrument_id")
    weighted = _latest(facts, WEIGHTED).set_index("instrument_id")
    later = weighted["filed"].reindex(dei.index)
    keep = later.isna() | (dei["filed"] >= later.fillna(dei["filed"]))
    dei = dei[keep.to_numpy()]
    ifrs = _latest(facts, IFRS).set_index("instrument_id")
    ifrs = ifrs[ifrs.index.astype(str).isin(ifrs_ids or set())]
    chosen = pd.concat([dei, weighted[~weighted.index.isin(dei.index)]])
    chosen = pd.concat([chosen, ifrs[~ifrs.index.isin(chosen.index)]])
    return chosen.reset_index()[columns].sort_values("instrument_id").reset_index(drop=True)


def year_ago(
    facts: pd.DataFrame | None, chosen: pd.DataFrame, ifrs_ids: set[str] | None = None
) -> pd.DataFrame:
    """Per chosen count: the count of the same concept a year earlier among ``facts`` (already
    public by the session's close): the fact whose period ended ``YEAR_AGO`` days before the
    chosen count's, the one closest to ``YEAR``, the latest filed on a tie. Columns as
    ``choose``; instruments with no such count are absent."""
    columns = ["instrument_id", "shares", "period_end", "filed", "concept"]
    if facts is None or facts.empty or chosen.empty:
        return pd.DataFrame(columns=columns)
    now = chosen[["instrument_id", "concept", "period_end"]].rename(columns={"period_end": "now"})
    now = now.assign(now=pd.to_datetime(now["now"]))
    ids = facts["instrument_id"].astype(str)
    past = facts[
        facts["concept"].isin([DEI, WEIGHTED])
        | (facts["concept"].eq(IFRS) & ids.isin(ifrs_ids or set()))
    ]
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
    after = np.where(
        chosen["concept"] == DEI, chosen["period_end"], chosen["filed"]
    )  # else weighted
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
    ifrs_ids = ifrs_allowed(inputs.get(REFERENCE))
    chosen = choose(inputs.get(SHARES), ifrs_ids)
    before = year_ago(inputs.get(SHARES), chosen, ifrs_ids)
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
    "SEC acceptance) and its status",
    (
        Input(PRICE_STATS),
        Input(SHARES, required=False),
        Input(REFERENCE, required=False),
        Input(SPLITS, lookback=split_lookback, required=False),
    ),
    FEATURES,
    compute,
    FundamentalsParams(),
    applies_to="operating_company",
)
