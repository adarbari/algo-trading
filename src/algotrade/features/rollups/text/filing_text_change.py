"""``filing_text_change@v1``: how much the latest 10-K / 10-Q of each operating company reads like
its year-ago filing (``comparison.py``; the inputs of the edges on filing-text change, EB F).

Input: ``events/filing_text`` as ``data.filing_text.recent`` hands it for the session: the Item
sections of every periodic filing of a company that filed in the last ``RECENT_SESSIONS``
sessions, with the filings of the year before, each as the session could see it (a filing
accepted after the close is visible from the next session). Sparse: a row for each company whose
latest periodic filing became known in the last five sessions, one per instrument of its ``cik``
(a company with two share classes gives each the same row), and only where the company maps to an
instrument at the session. Delisted names have no instrument and no row.

``ftc_status`` says what the row holds: ``OK`` (the measures below), ``NO_PRIOR`` (no filing of
the same form 330 to 400 days earlier is stored) or ``NOT_COMPARABLE`` (no item passes, or the
compared words are under the floor); every measure is null unless it is ``OK``. The carried
per-instrument view is ``filing_text_similarity@v1``, which reads this group.
"""

from datetime import date

import pandas as pd

from algotrade.core.time.calendar import sessions_ending
from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.text.comparison import RECENT_SESSIONS, compare_filings

NAME = "filing_text_change"
VERSION = 1
FILING_TEXT = "events/filing_text"
_INPUTS = tuple(
    f"{FILING_TEXT}.{c}"
    for c in ("form", "accession", "report_date", "known_from", "item", "quality", "text")
)
_NONE = (
    "no 10-K or 10-Q of the company became known in the last five sessions, or the status is not "
    "OK (no filing of the year before is stored, or too little comparable text): never read as "
    "no change"
)
FEATURES = (
    Feature("ftc_accession", "str", "category",
            "The SEC accession number of the company's latest 10-K or 10-Q known in the last five "
            "sessions", "no 10-K or 10-Q became known in the last five sessions",
            inputs=_INPUTS),
    Feature("ftc_prior_accession", "str", "category",
            "The accession number of the filing it was compared with: the same form, report date "
            "330 to 400 days earlier", "no such filing is stored (status NO_PRIOR), or no filing "
            "became known in the last five sessions", inputs=_INPUTS),
    Feature("ftc_form", "str", "category", "The form of the latest filing: 10-K or 10-Q",
            "no 10-K or 10-Q became known in the last five sessions", inputs=_INPUTS),
    Feature("ftc_known_from", "date", "date",
            "The session the filing became known: the first whose close follows SEC's acceptance",
            "no 10-K or 10-Q became known in the last five sessions", inputs=_INPUTS),
    Feature("ftc_cosine", "float32", "decimal",
            "Cosine of the raw word counts of the compared Item sections, new filing against the "
            "year-ago one; 1 is the same words in the same proportions, lower is more rewritten",
            _NONE, valid_range=(0, 1), inputs=_INPUTS),
    Feature("ftc_jaccard", "float32", "decimal",
            "Share of distinct words the two filings have in common (Jaccard on the word sets); "
            "1 is the same vocabulary", _NONE, valid_range=(0, 1), inputs=_INPUTS),
    Feature("ftc_items_compared", "int", "count",
            "How many Item sections were compared: those of the form (10-K: 1, 1A, 3, 7; 10-Q: "
            "I-2, II-1A) that are OK and at least 100 words in both filings",
            _NONE, valid_range=(0, None), inputs=_INPUTS),
    Feature("ftc_rf_cosine", "float32", "decimal",
            "Cosine of the 10-K Item 1A (risk factors) word counts against the year before",
            _NONE + "; or the form is a 10-Q, or Item 1A is not comparable in both 10-Ks",
            valid_range=(0, 1), inputs=_INPUTS),
    Feature("ftc_rf_len_change", "float32", "decimal",
            "Change in the length of the 10-K risk factors: new words over year-ago words, minus "
            "one; 0.2 is 20% longer", _NONE + "; or the form is a 10-Q, or Item 1A is not "
            "comparable in both 10-Ks", valid_range=(-1, None), inputs=_INPUTS),
    Feature("ftc_status", "str", "category",
            "OK (the measures are set), NO_PRIOR (no filing 330 to 400 days earlier is stored) or "
            "NOT_COMPARABLE (no item passes the floors)",
            "no 10-K or 10-Q became known in the last five sessions", inputs=_INPUTS),
)  # fmt: skip
COLUMNS = column_types(FEATURES)
_MEASURES = {
    "ftc_cosine": "cosine",
    "ftc_jaccard": "jaccard",
    "ftc_items_compared": "items_compared",
    "ftc_rf_cosine": "rf_cosine",
    "ftc_rf_len_change": "rf_len_change",
}


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(FILING_TEXT)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    stored = stored[stored["instrument_id"].notna()]
    recent_from = sessions_ending(session, RECENT_SESSIONS)[0]
    rows = []
    for c in compare_filings(stored, recent_from, session):
        ids = stored.loc[
            (stored["cik"] == c.cik) & (stored["accession"] == c.accession), "instrument_id"
        ]
        for iid in sorted(set(ids.astype(str))):
            row: dict[str, object] = {
                "instrument_id": iid, "ftc_accession": c.accession,
                "ftc_prior_accession": c.prior_accession, "ftc_form": c.form,
                "ftc_known_from": c.known_from, "ftc_status": c.status,
            }  # fmt: skip
            row.update({col: getattr(c, attr) for col, attr in _MEASURES.items()})
            rows.append(row)
    return pd.DataFrame(rows, columns=columns)


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "How much each company's latest 10-K or 10-Q (known in the last five sessions) reads like its "
    "year-ago filing: cosine and Jaccard of the Item sections, the risk factors on their own",
    (Input(FILING_TEXT, lookback=0, required=False),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
