"""``filing_events@v1``: how long ago each kind of SEC event filing was made public (the fields the
``on_event:filing_8k:<item>``, ``nt_late_filing`` and ``tender_offer`` schedules read, ADR 0050,
ADR 0053 amendment, EB H4).

Input: ``events/filing`` by the SESSION EACH FILING BECAME KNOWN (``data.events.
acceptance_sessions``: the first session whose close is strictly after SEC's acceptance instant;
a 16:30 filing counts from the next session, a weekend one from Monday), recomputed from the
stored ``ts``, never the stored ``known_from``, so a row stamped before the rule was fixed
cannot leak: only filings known on or before the session, no further back than ``LOOKBACK``
sessions. An amendment (8-K/A) is no new event; only the original 8-K counts.

Per kind, the latest known filing of it per instrument:

    sessions_since_8k_<item>   exchange sessions from the session the latest 8-K carrying Item
                               <item> became known up to the session (0: it became known today)
    last_8k_<item>_date        that session (the event's anchor, never the filing's own date)
    sessions_since_late_filing / last_late_filing_date      NT 10-K or NT 10-Q (12b-25)
    sessions_since_tender_offer / last_tender_offer_date    SC TO-I (the issuer's) or SC TO-T
                                                            (a third party's)

The 8-K items are ``ITEMS``: the ones with a documented price story (1.02 termination of a
material agreement, 2.05 exit or disposal costs, 3.01 delisting or listing-standard notice, 4.01
auditor change, 4.02 non-reliance on prior financials, 5.02 director or officer departure). A
filing carries several items ("5.02,9.01"): it counts for each one it names. A kind with no
filing in the window has a null; an instrument with none has no row (UNKNOWN, never "no event").
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_to
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature

NAME = "filing_events"
VERSION = 1
EVENTS = "events/filing"
LOOKBACK = 60  # sessions of filings loaded: the schedule needs the last few weeks
ITEMS = {  # 8-K item -> what it reports
    "1.02": "termination of a material agreement",
    "2.05": "exit or disposal costs (a restructuring)",
    "3.01": "a delisting or listing-standard notice",
    "4.01": "a change of the auditor",
    "4.02": "non-reliance on previously issued financial statements",
    "5.02": "the departure or appointment of a director or an officer",
}
EIGHT_K = "8-K"
LATE_FORMS = ("NT 10-K", "NT 10-Q")
TENDER_FORMS = ("SC TO-I", "SC TO-T")
KIND_FORMS = {"late_filing": LATE_FORMS, "tender_offer": TENDER_FORMS}  # column stem -> forms


def item_key(item: str) -> str:
    """The column stem of an 8-K item: ``4.02`` -> ``4_02``."""
    return item.replace(".", "_")


_INPUTS = (f"{EVENTS}.ts", f"{EVENTS}.form", f"{EVENTS}.items")


def _pair(stem: str, what: str, null: str) -> tuple[Feature, Feature]:
    return (
        Feature(
            f"sessions_since_{stem}", "int", "sessions",
            f"Exchange sessions from the session the latest {what} became known up to the "
            "session (0: it became known today)",
            null, valid_range=(0, None), inputs=_INPUTS,
        ),
        Feature(
            f"last_{stem}_date", "date", "date",
            f"The session the latest {what} became known (after the close of the session its "
            "filing was accepted in, else the next)",
            null, inputs=_INPUTS,
        ),
    )  # fmt: skip


def _none(what: str) -> str:
    return f"no {what} became known in the last {LOOKBACK} sessions"


FEATURES = (
    *(
        f
        for item, what in ITEMS.items()
        for f in _pair(
            f"8k_{item_key(item)}", f"8-K with Item {item} ({what})", _none(f"8-K with Item {item}")
        )
    ),
    *_pair("late_filing", "NT 10-K or NT 10-Q late-filing notice", _none("late-filing notice")),
    *_pair("tender_offer", "SC TO-I or SC TO-T tender offer", _none("tender offer")),
)
COLUMNS = column_types(FEATURES)


def _latest(rows: pd.DataFrame) -> pd.Series:
    """The latest ``event_date`` per instrument (an object Series of dates)."""
    return rows.groupby("instrument_id")["event_date"].max()


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(EVENTS)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    rows = stored[stored["event_date"] <= session]
    latest: dict[str, pd.Series] = {}
    eight = rows[rows["form"] == EIGHT_K]
    listed = eight["items"].fillna("").astype(str).str.split(",")
    items = eight.assign(item=listed.map(lambda names: [i.strip() for i in names])).explode("item")
    for item in ITEMS:
        latest[f"8k_{item_key(item)}"] = _latest(items[items["item"] == item])
    for stem, forms in KIND_FORMS.items():
        latest[stem] = _latest(rows[rows["form"].isin(forms)])
    ids = sorted(set().union(*(s.index for s in latest.values())))
    if not ids:
        return pd.DataFrame(columns=columns)
    out: dict[str, object] = {"instrument_id": pd.Index(ids).astype(str).to_numpy()}
    for stem, days in latest.items():
        known = [days.get(i) for i in ids]
        out[f"last_{stem}_date"] = known
        out[f"sessions_since_{stem}"] = pd.array(
            [None if d is None else sessions_to(d, session) for d in known], dtype="Int64"
        )
    return pd.DataFrame(out)[columns].reset_index(drop=True)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Sessions since each kind of SEC event filing (8-K items, late-filing notices, tender "
    "offers) became known",
    (Input(EVENTS, lookback=LOOKBACK, required=False),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
