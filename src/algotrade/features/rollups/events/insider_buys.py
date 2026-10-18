"""``insider_buys@v1``: open-market insider purchases known in the last 30 days, and whether they
look opportunistic (the inputs of the edge ``insider_opportunistic_cluster_buys``, EB E6).

Input: ``events/insider_transaction`` (Form 4 lines, ADR 0050 amendment, EB D6) as
``data.insiders.buyer_histories`` hands it: per session, the open-market lines (code P purchase,
code S sale, never a derivative) of each (issuer, owner) with a purchase known in the last
``BUY_WINDOW_DAYS`` calendar days, each line as that session could see it. A line is known from
``known_from``, the first session whose close follows SEC's acceptance (a filing accepted after
the close counts from the next session); a purchase is counted from there, never from its
transaction date.

Per instrument with a purchase in the window (a name with none has no row: UNKNOWN, never "no
buying"):

    insider_cluster_buy_count   distinct owners with a purchase known in the window (a cluster is
                                three or more; the practitioner rule, not a stored threshold)
    insider_opportunistic_flag  an owner who bought is opportunistic (Cohen, Malloy and
                                Pomorski 2012): true when one is; false when every classified
                                buyer is routine; null when no buyer can be classified
    plan_10b5_1_flag            a purchase in the window was made under a Rule 10b5-1 plan

Routine (Cohen, Malloy and Pomorski): the owner traded (bought or sold) in the same calendar
month of each of the three years before the purchase's year. An owner is classified only with
a trade in the store in or before the year three years before the purchase's year; an owner
with a shorter record is unclassified, never opportunistic by default. Their trade is the
transaction date of an open-market line known by the session.
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "insider_buys"
VERSION = 1
EVENTS = "events/insider_transaction"
BUY_WINDOW_DAYS = 30  # equals data.insiders.reading.BUY_WINDOW_DAYS (tested)
PURCHASE = "P"
YEARS = 3  # the routine rule's look-back years

_INPUTS = (
    f"{EVENTS}.transaction_code", f"{EVENTS}.owner_cik", f"{EVENTS}.known_from",
    f"{EVENTS}.transaction_date",
)  # fmt: skip
_NONE = (
    f"no open-market insider purchase became known in the last {BUY_WINDOW_DAYS} days, or no "
    "Form 4 history is stored for the session: never read as no insider buying"
)
FEATURES = (
    Feature(
        "insider_cluster_buy_count", "int", "count",
        f"Distinct insiders with an open-market purchase (Form 4 code P) that became known in the "
        f"last {BUY_WINDOW_DAYS} calendar days; three or more is a cluster",
        _NONE, valid_range=(0, None), inputs=_INPUTS,
    ),
    Feature(
        "insider_opportunistic_flag", "bool", "flag",
        "A buyer in the window is an opportunistic trader, not a routine one: true when one is; "
        "false when every classified buyer is routine (traded in the same calendar month in each "
        "of the three previous years, Cohen, Malloy and Pomorski 2012)",
        _NONE + "; or no buyer has a Form 4 record reaching three years before the purchase's "
        "year (unclassified)", inputs=(*_INPUTS, f"{EVENTS}.derivative"),
    ),
    Feature(
        "plan_10b5_1_flag", "bool", "flag",
        "A purchase in the window was made under a Rule 10b5-1 trading plan (the filing's own "
        "checkbox, on Form 4 since April 2023)",
        _NONE + "; or no purchase in the window carries the checkbox (a filing before April 2023)",
        inputs=(*_INPUTS, f"{EVENTS}.plan_10b5_1"),
    ),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _traded_months(history: pd.DataFrame) -> dict[tuple[str, str], set[tuple[int, int]]]:
    """``(instrument_id, owner_cik)`` -> the (year, month) of each open-market trade."""
    months: dict[tuple[str, str], set[tuple[int, int]]] = {}
    for iid, owner, traded in zip(
        history["instrument_id"], history["owner_cik"], history["transaction_date"], strict=True
    ):
        day = pd.Timestamp(traded)
        months.setdefault((str(iid), str(owner)), set()).add((day.year, day.month))
    return months


def _classes(buys: pd.DataFrame, history: pd.DataFrame) -> pd.Series:
    """Each purchase's class: ``True`` opportunistic, ``False`` routine, ``None`` unclassified."""
    months = _traded_months(history)
    out: list[bool | None] = []
    for iid, owner, traded in zip(
        buys["instrument_id"], buys["owner_cik"], buys["transaction_date"], strict=True
    ):
        trades = months.get((str(iid), str(owner)), set())
        day = pd.Timestamp(traded)
        if not trades or min(y for y, _ in trades) > day.year - YEARS:
            out.append(None)  # a record too short to call
        else:
            routine = all((day.year - k, day.month) in trades for k in range(1, YEARS + 1))
            out.append(not routine)
    return pd.Series(out, index=buys.index, dtype=object)


def _any_true(values: pd.Series) -> bool | None:
    """True when any value is true; false when some are known and none true; null when none."""
    known = values.dropna()
    return None if known.empty else bool(known.astype(bool).any())


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(EVENTS)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    history = stored[stored["as_of"] == session]
    since = pd.Timestamp(session) - pd.Timedelta(days=BUY_WINDOW_DAYS)
    recent = pd.to_datetime(history["known_from"]) > since
    buys = history[recent & (history["transaction_code"] == PURCHASE) & ~history["derivative"]]
    if buys.empty:
        return pd.DataFrame(columns=columns)
    buys = buys.assign(_class=_classes(buys, history))
    grouped = buys.groupby("instrument_id")
    out = pd.DataFrame(
        {
            "insider_cluster_buy_count": grouped["owner_cik"].nunique(),
            "insider_opportunistic_flag": grouped["_class"].agg(_any_true),
            "plan_10b5_1_flag": grouped["plan_10b5_1"].agg(_any_true),
        }
    )
    return out.rename_axis("instrument_id").reset_index()[columns]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Open-market insider purchases known in the last 30 days: how many insiders, whether they are "
    "opportunistic, whether under a 10b5-1 plan",
    (Input(EVENTS, lookback=0, required=False),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
