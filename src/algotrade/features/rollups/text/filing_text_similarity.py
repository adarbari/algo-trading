"""``filing_text_similarity@v1``: each operating company's latest filing-text similarity, carried
until the next filing (the inputs of the edges on filing-text change, EB F).

Input: this table's source group ``filing_text_change@v1`` over the last ``LOOKBACK`` sessions
(a 10-K carries 400 calendar days, a 10-Q 150, so a session's latest filing is in there). Per
instrument:

    text_sim_*          from the latest periodic filing of either form, carried at most
                        ``CARRY_DAYS`` calendar days from the session it became known
    risk_factor_*       from the latest 10-K (the source's ``ftc_k_*``, which a 10-Q accepted in
                        the same window does not hide), carried at most ``RISK_CARRY_DAYS`` days

Past the cap the part has no value (a name with neither has no row: UNKNOWN, as ``insider_buys``).
``*_status`` is the filing's own (``OK``, ``NO_PRIOR``, ``NOT_COMPARABLE``); the measures are null
unless it is ``OK``, so a screen on ``text_sim_status = OK`` never reads a missing value as
similar. The risk-factor status is ``NOT_COMPARABLE`` when the filing is a comparable 10-K whose
Item 1A is not (missing, short or not OK in one of the two years).
"""

from datetime import date

import pandas as pd

from algotrade.features.framework.declaration import FeatureGroup, Input, Inputs, column_types
from algotrade.features.framework.feature import Feature
from algotrade.features.rollups.text.comparison import NOT_COMPARABLE, OK
from algotrade.features.rollups.text.filing_text_change import GROUP as CHANGE

NAME = "filing_text_similarity"
VERSION = 1
SOURCE = CHANGE.table
LOOKBACK = 280  # sessions: 400 calendar days, the longest carry, with margin
CARRY_DAYS = 150
RISK_CARRY_DAYS = 400
_SRC = ("filing_text_change.ftc_cosine@v1", "filing_text_change.ftc_k_rf_cosine@v1")
_NONE = (
    "no 10-K or 10-Q became known in the carry window, or its status is not OK (no filing of the "
    "year before is stored, or too little comparable text): never read as no change"
)
_RISK_NONE = (
    "no 10-K became known in the last 400 days, or its status is not OK, or Item 1A is not "
    "comparable in both years: never read as no change"
)
FEATURES = (
    Feature("text_sim_cosine", "float32", "decimal",
            "Cosine of the raw word counts of the latest 10-K or 10-Q against the year-ago "
            "filing's, carried 150 days; 1 is unchanged text, lower is more rewritten",
            _NONE, valid_range=(0, 1), inputs=_SRC),
    Feature("text_sim_jaccard", "float32", "decimal",
            "Share of distinct words the latest filing and its year-ago filing have in common, "
            "carried 150 days", _NONE, valid_range=(0, 1), inputs=_SRC),
    Feature("text_sim_form", "str", "category", "The form the text similarity is of: 10-K or 10-Q",
            "no 10-K or 10-Q became known in the last 150 days", inputs=_SRC),
    Feature("text_sim_known_from", "date", "date",
            "The session that filing became known (the first whose close follows SEC's "
            "acceptance)", "no 10-K or 10-Q became known in the last 150 days", inputs=_SRC),
    Feature("text_sim_status", "str", "category",
            "OK, NO_PRIOR (no filing of the year before is stored) or NOT_COMPARABLE (too little "
            "comparable text)", "no 10-K or 10-Q became known in the last 150 days", inputs=_SRC),
    Feature("risk_factor_sim_cosine", "float32", "decimal",
            "Cosine of the 10-K risk factors (Item 1A) word counts against the year before, "
            "carried 400 days; 1 is unchanged", _RISK_NONE, valid_range=(0, 1), inputs=_SRC),
    Feature("risk_factor_len_change", "float32", "decimal",
            "Change in the length of the 10-K risk factors, new words over year-ago words minus "
            "one, carried 400 days; 0.2 is 20% longer", _RISK_NONE, valid_range=(-1, None),
            inputs=_SRC),
    Feature("risk_factor_status", "str", "category",
            "OK, NO_PRIOR or NOT_COMPARABLE for the latest 10-K's risk factors",
            "no 10-K became known in the last 400 days", inputs=_SRC),
)  # fmt: skip
COLUMNS = column_types(FEATURES)


def _latest(rows: pd.DataFrame, session: date, days: int, prefix: str) -> pd.DataFrame:
    """The latest filing per instrument (``<prefix>known_from``, then accession) no more than
    ``days`` calendar days before the session and not after it; ``prefix`` picks the latest
    filing of either form (``ftc_``) or the latest 10-K (``ftc_k_``)."""
    known = pd.to_datetime(rows[f"{prefix}known_from"])
    since = pd.Timestamp(session) - pd.Timedelta(days=days)
    rows = rows[(known >= since) & (known <= pd.Timestamp(session))]
    ordered = rows.sort_values(
        [f"{prefix}known_from", f"{prefix}accession", "session_date"], kind="stable"
    )
    return ordered.drop_duplicates("instrument_id", keep="last").set_index("instrument_id")


def _risk_status(row: pd.Series) -> str:
    if row["ftc_k_status"] == OK and pd.isna(row["ftc_k_rf_cosine"]):
        return NOT_COMPARABLE
    return str(row["ftc_k_status"])


def compute(inputs: Inputs, session: date, params: None) -> pd.DataFrame:
    columns = ["instrument_id", *COLUMNS]
    stored = inputs.get(SOURCE)
    if stored is None or stored.empty:
        return pd.DataFrame(columns=columns)
    text = _latest(stored, session, CARRY_DAYS, "ftc_")
    risk = _latest(stored, session, RISK_CARRY_DAYS, "ftc_k_")
    out = pd.DataFrame(index=text.index.union(risk.index))
    out.index.name = "instrument_id"
    for col, src in (("text_sim_cosine", "ftc_cosine"), ("text_sim_jaccard", "ftc_jaccard"),
                     ("text_sim_form", "ftc_form"), ("text_sim_known_from", "ftc_known_from"),
                     ("text_sim_status", "ftc_status")):  # fmt: skip
        out[col] = text[src].reindex(out.index)
    out["risk_factor_sim_cosine"] = risk["ftc_k_rf_cosine"].reindex(out.index)
    out["risk_factor_len_change"] = risk["ftc_k_rf_len_change"].reindex(out.index)
    out["risk_factor_status"] = (
        risk.apply(_risk_status, axis=1).reindex(out.index) if len(risk) else None
    )
    return out.reset_index()[columns]


GROUP = FeatureGroup(
    NAME,
    VERSION,
    "Each company's latest filing-text similarity to its year-ago filing, carried until the next "
    "one: 150 days for the 10-K or 10-Q, 400 for the 10-K risk factors",
    (Input(SOURCE, lookback=LOOKBACK, required=False),),
    FEATURES,
    compute,
    applies_to="operating_company",
)
